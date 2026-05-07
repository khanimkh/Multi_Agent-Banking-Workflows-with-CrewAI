from __future__ import annotations

import ast
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import re
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .content_pipeline import run_content_pipeline
from .flow_kickoff import run_flow_kickoff
from .main import run_primary_workflows


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

app = FastAPI(title="Bank Assistant CrewAI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PrimaryRequest(BaseModel):
    customer_name: str = Field(default="Alex Morgan")
    customer_goal: str = Field(default="reduce monthly credit card debt")
    region: str = Field(default="US")
    risk_level: str = Field(default="medium")


class ContentRequest(BaseModel):
    subject: str = Field(default="responsible use of AI agents in retail banking")
    region: str = Field(default="US")


def _strip_markdown_fences(text: str) -> str:
    """
    Removes surrounding Markdown code fences from a string.

    If ``text`` starts with a triple-backtick fence (`` ``` `` optionally
    followed by a language tag), the opening and closing fence lines are
    stripped so only the inner content remains.

    Parameters:
        text (str): Raw text that may be wrapped in a Markdown code block.

    Returns:
        str: The text with leading/trailing fences removed. Returns the
        original stripped text unchanged if no fence is found.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _capture_sync(func, *args, **kwargs):
    """
    Calls a synchronous function and captures everything it prints to stdout
    and stderr into a string buffer.

    Parameters:
        func       : The synchronous callable to invoke.
        *args      : Positional arguments forwarded to ``func``.
        **kwargs   : Keyword arguments forwarded to ``func``.

    Returns:
        tuple[Any, str]: A 2-tuple of ``(return_value, captured_output)``
        where ``return_value`` is whatever ``func`` returned and
        ``captured_output`` is the combined stdout + stderr text.
    """
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


async def _capture_async(func, *args, **kwargs):
    """
    Awaits an async function and captures everything it prints to stdout
    and stderr into a string buffer.

    Parameters:
        func       : The async callable (coroutine function) to await.
        *args      : Positional arguments forwarded to ``func``.
        **kwargs   : Keyword arguments forwarded to ``func``.

    Returns:
        tuple[Any, str]: A 2-tuple of ``(return_value, captured_output)``
        where ``return_value`` is whatever ``func`` returned and
        ``captured_output`` is the combined stdout + stderr text.
    """
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = await func(*args, **kwargs)
    return result, buffer.getvalue()


def _read_if_exists(path_str: str) -> str:
    """
    Reads a file from disk and returns its text content, or an empty string
    if the file does not exist or the path points to a directory.

    Parameters:
        path_str (str): Absolute or relative path to the file to read.

    Returns:
        str: Full UTF-8 text content of the file, or ``""`` if the file
        is missing or is not a regular file.
    """
    path = Path(path_str)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _json_to_markdown(value: dict | list | str) -> str:
    """
    Converts a value to a Markdown-formatted JSON code block.

    If ``value`` is already a string it is returned unchanged. Otherwise
    it is serialised with ``json.dumps`` and wrapped in a fenced code block.

    Parameters:
        value (dict | list | str): The value to format.

    Returns:
        str: A Markdown JSON code block, or the original string if ``value``
        is already a ``str``.
    """
    if isinstance(value, str):
        return value
    return "```json\n" + json.dumps(value, indent=2) + "\n```"


def _extract_literal_field(text: str, field_name: str, stop_fields: list[str]) -> object | None:
    """
    Extracts and Python-evaluates a single named field value from a
    ``CrewOutput(...)`` repr string.

    Locates ``field_name=<value>`` inside ``text``, then finds the earliest
    ``", <stop_field>=`` token to determine where the value ends, and calls
    ``ast.literal_eval`` on the extracted snippet.

    Parameters:
        text        (str)        : The full repr string to search inside.
        field_name  (str)        : Name of the field to extract
                                   (e.g. ``"raw"``, ``"json_dict"``).
        stop_fields (list[str])  : Other field names whose ``", name="``
                                   pattern marks the end of the target value.

    Returns:
        The Python object produced by ``ast.literal_eval``, or ``None`` if
        the field is not found or the snippet cannot be evaluated.
    """
    if f"{field_name}=" not in text:
        return None

    start = text.index(f"{field_name}=") + len(field_name) + 1
    end = len(text)
    for stop_field in stop_fields:
        token = f", {stop_field}="
        token_index = text.find(token, start)
        if token_index != -1:
            end = min(end, token_index)
    snippet = text[start:end].rstrip(") ")
    try:
        return ast.literal_eval(snippet)
    except Exception:
        return None


def _extract_crewoutput_payloads(text: str) -> list[object]:
    """
    Scans ``text`` for all ``raw=<value>`` occurrences inside CrewAI output
    repr strings and returns the parsed values as a list.

    Each ``raw=`` snippet is extracted up to the nearest known delimiter
    (``pydantic=``, ``json_dict=``, ``tasks_output=``, ``token_usage=``),
    evaluated with ``ast.literal_eval``, then optionally JSON-parsed if the
    result is a string.

    Parameters:
        text (str): A string that may contain one or more
                    ``CrewOutput(raw=..., ...)`` repr fragments.

    Returns:
        list[object]: Parsed payload values in the order they appear.
        Each element may be a ``dict``, ``list``, or ``str`` depending on
        the content of the ``raw`` field.
    """
    payloads: list[object] = []
    search_from = 0

    while True:
        raw_index = text.find("raw=", search_from)
        if raw_index == -1:
            break

        start = raw_index + len("raw=")
        end_candidates = []
        for token in [", pydantic=", ", json_dict=", ", tasks_output=", ", token_usage="]:
            token_index = text.find(token, start)
            if token_index != -1:
                end_candidates.append(token_index)

        if not end_candidates:
            break

        snippet = text[start:min(end_candidates)].strip()
        try:
            literal = ast.literal_eval(snippet)
        except Exception:
            search_from = start
            continue

        if isinstance(literal, str):
            try:
                payloads.append(json.loads(literal))
            except Exception:
                payloads.append(literal)
        else:
            payloads.append(literal)

        search_from = min(end_candidates)

    return payloads


def _coerce_structured_value(value: object) -> object:
    """
    Attempts to convert an arbitrary crew output value into a structured
    Python object (``dict`` or ``list``) by trying several parsing strategies
    in order:

    1. If already a ``dict`` or ``list``, return as-is.
    2. Strip Markdown code fences, then try ``json.loads``.
    3. If the string starts with ``CrewOutput(``, extract ``json_dict=``
       or ``raw=`` using ``_extract_literal_field``.
    4. If the string contains ``CrewOutput(``, scan all ``raw=`` payloads
       with ``_extract_crewoutput_payloads``.
    5. Return the plain string as a fallback.

    Parameters:
        value (object): The raw value from a crew result — may be a
                        ``dict``, ``list``, ``str``, or CrewAI object repr.

    Returns:
        object: A ``dict``, ``list``, ``str``, or other value that best
        represents the structured content of ``value``.
    """
    if isinstance(value, dict) or isinstance(value, list):
        return value
    if not isinstance(value, str):
        return value

    text = _strip_markdown_fences(value)
    if not text:
        return ""

    try:
        return json.loads(text)
    except Exception:
        pass

    if text.startswith("CrewOutput("):
        json_dict = _extract_literal_field(text, "json_dict", ["pydantic", "tasks_output", "token_usage", "raw"])
        if isinstance(json_dict, dict):
            return json_dict

        raw_value = _extract_literal_field(text, "raw", ["pydantic", "json_dict", "tasks_output", "token_usage"])
        if isinstance(raw_value, str):
            try:
                return json.loads(raw_value)
            except Exception:
                return raw_value

    if "CrewOutput(" in text:
        payloads = _extract_crewoutput_payloads(text)
        if payloads:
            return payloads

    return text


def _format_structured_markdown(value: object) -> str:
    """
    Converts a crew output value into a human-readable Markdown string.

    First calls ``_coerce_structured_value`` to parse the value, then
    renders the result:
    - ``dict``  → bullet list of ``- Key: value`` lines; list values are
      expanded as sub-bullets.
    - ``list``  → numbered ``### Item N`` sections, each recursively
      formatted.
    - ``str``   → stripped plain text with any leading ``CrewOutput(...)``
      wrapper removed.

    Parameters:
        value (object): Raw crew output value — dict, list, string, or repr.

    Returns:
        str: Formatted Markdown text, or ``"No content returned."`` if the
        result is empty.
    """
    structured = _coerce_structured_value(value)

    if isinstance(structured, dict):
        lines: list[str] = []
        for key, raw in structured.items():
            label = key.replace("_", " ").title()
            if isinstance(raw, list):
                lines.append(f"- {label}:")
                if raw:
                    lines.extend(f"- {item}" for item in raw)
                else:
                    lines.append("- None")
            else:
                lines.append(f"- {label}: {raw}")
        return "\n".join(lines).strip()

    if isinstance(structured, list):
        if not structured:
            return "- None"
        blocks: list[str] = []
        for index, item in enumerate(structured, 1):
            formatted_item = _format_structured_markdown(item)
            if isinstance(item, dict):
                blocks.append(f"### Item {index}\n{formatted_item}")
            else:
                blocks.append(f"### Item {index}\n- {formatted_item}")
        return "\n\n".join(blocks)

    text = str(structured).strip()
    text = re.sub(r"^CrewOutput\((.*)\)$", r"\1", text, flags=re.DOTALL)
    return text or "No content returned."


def _build_sales_flow_markdown(result: dict) -> str:
    """
    Builds a Markdown report string from a completed sales flow result.

    Reads the JSON summary file written by ``BankSalesFlow.save_run_summary()``
    and formats lead counts, high-priority lead details, and email outputs
    into a structured Markdown document.

    Parameters:
        result (dict): The return value of ``run_flow_kickoff()``. Expected
                       key: ``output_path`` (str) — path to the JSON summary
                       file. Other keys are ignored.

    Returns:
        str: A Markdown string with sections for Summary, High-Priority
        Leads, and Email Outputs. Falls back gracefully if the JSON file is
        missing or malformed.
    """
    output_path = result.get("output_path", "")
    scored_leads: list[dict] = []
    high_priority_leads: list[dict] = []
    emails: list[dict | str] = []

    if output_path:
        try:
            payload = json.loads(_read_if_exists(output_path) or "{}")
            scored_leads = payload.get("scored_leads", []) or []
            high_priority_leads = payload.get("high_priority_leads", []) or []
            emails = payload.get("emails", []) or []
        except Exception:
            pass

    lines = [
        "# Sales Flow Report",
        "",
        "## Summary",
        f"- Scored leads: {len(scored_leads)}",
        f"- High-priority leads: {len(high_priority_leads)}",
        f"- Drafted follow-up emails: {len(emails)}",
        "",
        "## High-Priority Leads",
    ]

    if high_priority_leads:
        for index, lead in enumerate(high_priority_leads, 1):
            lines.append(f"### Lead {index}: {lead.get('name', 'Unknown')}")
            lines.append(f"- Region: {lead.get('region', 'N/A')}")
            lines.append(f"- Score: {lead.get('lead_score', 'N/A')}")
            lines.append(f"- Goal: {lead.get('goal', 'N/A')}")
            lines.append(f"- Segment: {lead.get('segment', 'N/A')}")
            lines.append("")
    else:
        lines.append("- No high-priority leads identified in this run.")

    lines.extend(["", "## Email Outputs"])
    if emails:
        for index, email in enumerate(emails, 1):
            if isinstance(email, dict):
                preview = email.get("raw", email)
            else:
                preview = email
            lines.append(f"### Email {index}")
            lines.append(_format_structured_markdown(preview))
            lines.append("")
    else:
        lines.append("- No email content generated.")

    return "\n".join(lines).strip() + "\n"


def _parse_social_posts_from_blog_tail(text: str) -> list[dict[str, str]]:
    """
    Extracts social media posts embedded at the end of a blog post string.

    Looks for lines matching the pattern ``- **Platform**: content`` using
    a regular expression and returns each match as a ``{platform, content}``
    dict. Used when social posts are appended inline to the blog output
    rather than stored in a separate file.

    Parameters:
        text (str): The tail portion of a blog post string that follows a
                    ``### Social Media Posts`` heading.

    Returns:
        list[dict[str, str]]: Parsed social post dicts, each with
        ``platform`` and ``content`` keys. Empty list if no matches found.
    """
    posts: list[dict[str, str]] = []
    for match in re.finditer(r"^-\s*\*\*(.+?)\*\*:\s*(.+)$", text, flags=re.MULTILINE):
        posts.append({"platform": match.group(1).strip(), "content": match.group(2).strip()})
    return posts


def _parse_social_posts_md(text: str) -> list[dict[str, str]]:
    """
    Parses social media posts from a Markdown file where each platform is
    a ``## Platform`` heading followed by the post content lines.

    Iterates through lines, collecting content under each ``##`` heading
    until the next heading or end of file. Skips the document title (``#``)
    and blank lines.

    Parameters:
        text (str): Full text content of a social posts Markdown file
                    (e.g. ``bank_social_posts.md``).

    Returns:
        list[dict[str, str]]: Parsed social post dicts with ``platform`` and
        ``content`` keys. Posts with empty content are excluded.
    """
    posts: list[dict[str, str]] = []
    current_platform = ""
    current_lines: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            if current_platform:
                posts.append({"platform": current_platform, "content": " ".join(current_lines).strip()})
            current_platform = line[3:].strip()
            current_lines = []
            continue
        if not line or line.startswith("# "):
            continue
        current_lines.append(line)

    if current_platform:
        posts.append({"platform": current_platform, "content": " ".join(current_lines).strip()})

    return [p for p in posts if p.get("content")]


def _build_content_markdown(result: dict) -> str:
    """
    Builds a Markdown report from a completed content pipeline result.

    Reads output files from the ``reports/`` directory using a priority order:
    1. ``bank_content_output.json`` — structured blog + social posts.
    2. ``bank_blog_post.md`` — blog post Markdown fallback.
    3. ``bank_social_posts.md`` — social posts Markdown fallback.
    4. ``result["raw_result"]`` — last-resort fallback from the crew output.

    Also handles the case where social posts are embedded at the end of the
    blog post under a ``### Social Media Posts`` heading.

    Parameters:
        result (dict): The return value of ``run_content_pipeline()``. Used
                       only as a last-resort fallback via ``raw_result`` key.

    Returns:
        str: A Markdown string with a Blog Post section and a Social Posts
        section. Each social post is rendered as a numbered ``### Post N``
        subsection.
    """
    content_json_path = ROOT / "reports" / "bank_content_output.json"
    blog_path = ROOT / "reports" / "bank_blog_post.md"
    social_path = ROOT / "reports" / "bank_social_posts.md"

    blog_post = ""
    social_posts: list[dict[str, str]] = []

    json_payload: dict = {}
    json_text = _read_if_exists(str(content_json_path))
    if json_text:
        try:
            json_payload = json.loads(json_text)
        except Exception:
            json_payload = {}

    if isinstance(json_payload.get("blog_post"), str):
        blog_post = _strip_markdown_fences(json_payload["blog_post"])

    if isinstance(json_payload.get("social_media_posts"), list):
        for item in json_payload["social_media_posts"]:
            if isinstance(item, dict):
                social_posts.append(
                    {
                        "platform": str(item.get("platform", "Platform")).strip(),
                        "content": str(item.get("content", "")).strip(),
                    }
                )

    if not blog_post:
        blog_post = _strip_markdown_fences(_read_if_exists(str(blog_path)))

    if "### Social Media Posts" in blog_post:
        blog_only, social_tail = blog_post.split("### Social Media Posts", 1)
        blog_post = blog_only.strip()
        if not social_posts:
            social_posts = _parse_social_posts_from_blog_tail(social_tail)

    if not social_posts:
        social_posts = _parse_social_posts_md(_read_if_exists(str(social_path)))

    if not blog_post:
        blog_post = _strip_markdown_fences(result.get("raw_result", ""))

    lines = ["# Content Pipeline Report", "", "## Blog Post", "", blog_post or "No blog post generated.", "", "## Social Posts", ""]

    if social_posts:
        for index, post in enumerate(social_posts, 1):
            platform = post.get("platform", "Platform") or "Platform"
            content = post.get("content", "").strip() or "No content."
            lines.append(f"### Post {index}: {platform}")
            lines.append(content)
            lines.append("")
    else:
        lines.append("- No social posts generated.")

    return "\n".join(lines).strip() + "\n"


class _LiveJobWriter(io.TextIOBase):
    """
    A writable ``TextIOBase`` stream that appends text in real time to a
    background job's ``process_log`` field in the ``JOBS`` dict.

    Used with ``redirect_stdout`` / ``redirect_stderr`` inside a worker
    thread so the web UI can poll ``GET /jobs/{job_id}`` for live output
    while the crew is still running.
    """

    def __init__(self, job_id: str):
        """
        Parameters:
            job_id (str): The hex job ID string used to look up the job
                          record in the global ``JOBS`` dict.
        """
        self.job_id = job_id

    def write(self, text: str) -> int:
        """
        Appends ``text`` to the job's ``process_log`` and updates its
        ``updated_at`` timestamp under the ``JOBS_LOCK``.

        Parameters:
            text (str): The text chunk written by the redirected stream.
                        Empty strings are ignored.

        Returns:
            int: Number of characters written (``len(text)``).
        """
        if not text:
            return 0
        with JOBS_LOCK:
            job = JOBS.get(self.job_id)
            if job is not None:
                job["process_log"] += text
                job["updated_at"] = time.time()
        return len(text)

    def flush(self) -> None:
        """
        No-op flush implementation required by the ``TextIOBase`` interface.
        The job log is written synchronously on every ``write()`` call so
        no buffering needs to be flushed.
        """
        return None


def _build_primary_response(result: dict, process_log: str) -> dict:
    """
    Assembles the final JSON response body for a completed primary-workflows
    run, combining advisory and risk outputs into a single Markdown document.

    If both workflow outputs are empty, falls back to reading the saved
    report Markdown file from disk.

    Parameters:
        result      (dict) : Return value of ``run_primary_workflows()``.
                             Expected keys: ``advisory_result``,
                             ``risk_result``, ``report_path``.
        process_log (str)  : Combined stdout + stderr captured during the
                             crew run, included in the response for display
                             in the web UI log panel.

    Returns:
        dict with keys:
            ``title``          (str)  — display label for the UI.
            ``process_log``    (str)  — captured console output.
            ``final_markdown`` (str)  — formatted Markdown report.
            ``details``        (dict) — raw ``result`` dict passed through.
    """
    advisory_text = _strip_markdown_fences(str(result.get("advisory_result", ""))).strip()
    risk_text = _strip_markdown_fences(str(result.get("risk_result", ""))).strip()

    final_markdown = "\n\n".join(
        [
            "# Customer Support and Advisory Report",
            "## Advisory and Service Workflow\n" + (advisory_text or "No advisory output generated."),
            "## Risk and Compliance Workflow\n" + (risk_text or "No risk output generated."),
        ]
    )

    if not advisory_text and not risk_text:
        report_text = _read_if_exists(result.get("report_path", ""))
        if report_text:
            final_markdown = _strip_markdown_fences(report_text)
    return {
        "title": "Primary Workflows",
        "process_log": process_log,
        "final_markdown": final_markdown,
        "details": result,
    }


def _start_primary_job(payload: PrimaryRequest) -> str:
    """
    Creates a background job record and launches a daemon thread to run
    the primary workflows asynchronously.

    The thread writes live output to ``JOBS[job_id]["process_log"]`` via
    ``_LiveJobWriter``. The caller can poll ``GET /jobs/{job_id}`` for
    status and results.

    Parameters:
        payload (PrimaryRequest): Validated request body containing
            ``customer_name``, ``customer_goal``, ``region``, and
            ``risk_level``.

    Returns:
        str: The hex job ID string that was created and queued.
    """
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "process_log": "",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def _worker() -> None:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "running"
            JOBS[job_id]["updated_at"] = time.time()

        writer = _LiveJobWriter(job_id)
        try:
            with redirect_stdout(writer), redirect_stderr(writer):
                result = run_primary_workflows(
                    customer_name=payload.customer_name,
                    customer_goal=payload.customer_goal,
                    region=payload.region,
                    risk_level=payload.risk_level,
                )
            with JOBS_LOCK:
                log_text = JOBS[job_id]["process_log"]
                JOBS[job_id]["result"] = _build_primary_response(result, log_text)
                JOBS[job_id]["status"] = "completed"
                JOBS[job_id]["updated_at"] = time.time()
        except Exception as exc:
            with JOBS_LOCK:
                JOBS[job_id]["error"] = str(exc)
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["updated_at"] = time.time()

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


@app.get("/health")
def health() -> dict[str, str]:
    """
    Liveness check endpoint.

    Used by Docker healthcheck and load balancers to verify the API process
    is running and responsive.

    Returns:
        dict: ``{"status": "ok"}``
    """
    return {"status": "ok"}


@app.get("/")
def serve_frontend() -> FileResponse:
    """
    Serves the single-page web application entry point.

    Returns:
        FileResponse: ``frontend/index.html``
    """
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/app.js")
def serve_frontend_js() -> FileResponse:
    """
    Serves the frontend JavaScript bundle.

    Returns:
        FileResponse: ``frontend/app.js`` with ``application/javascript``
        content type.
    """
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")


@app.get("/style.css")
def serve_frontend_css() -> FileResponse:
    """
    Serves the frontend stylesheet.

    Returns:
        FileResponse: ``frontend/style.css`` with ``text/css`` content type.
    """
    return FileResponse(FRONTEND_DIR / "style.css", media_type="text/css")


@app.post("/run/primary")
def run_primary(payload: PrimaryRequest) -> dict:
    """
    Runs both primary workflows synchronously and returns the full result
    in a single response (blocking until complete).

    Use ``POST /jobs/primary`` instead for long-running runs where a
    non-blocking response and live log polling are preferred.

    Request body (JSON):
        customer_name  (str, default "Alex Morgan")               : Customer full name.
        customer_goal  (str, default "reduce monthly credit card debt") : Financial goal.
        region         (str, default "US")                        : Geographic region.
        risk_level     (str, default "medium")                    : Risk classification hint.

    Returns:
        dict: Response from ``_build_primary_response()`` containing
        ``title``, ``process_log``, ``final_markdown``, and ``details``.

    Raises:
        HTTPException 500: If any workflow raises an unexpected exception.
    """
    try:
        result, process_log = _capture_sync(
            run_primary_workflows,
            customer_name=payload.customer_name,
            customer_goal=payload.customer_goal,
            region=payload.region,
            risk_level=payload.risk_level,
        )
        return _build_primary_response(result, process_log)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/jobs/primary")
def run_primary_job(payload: PrimaryRequest) -> dict[str, str]:
    """
    Enqueues the primary workflows as a background job and returns
    immediately with a job ID.

    The job runs in a daemon thread. Poll ``GET /jobs/{job_id}`` to check
    status and retrieve results or live log output.

    Request body (JSON): Same fields as ``POST /run/primary``.

    Returns:
        dict: ``{"job_id": "<hex>", "status": "queued"}``

    Raises:
        HTTPException 500: If the job could not be created.
    """
    try:
        job_id = _start_primary_job(payload)
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    """
    Returns the current state of a background job.

    Path parameter:
        job_id (str): Hex job ID returned by ``POST /jobs/primary``.

    Returns:
        dict with keys:
            ``job_id``      (str)        — the job identifier.
            ``status``      (str)        — ``"queued"``, ``"running"``,
                                           ``"completed"``, or ``"failed"``.
            ``process_log`` (str)        — live console output captured so far.
            ``result``      (dict|None)  — full result payload when completed.
            ``error``       (str|None)   — error message if the job failed.
            ``updated_at``  (float)      — Unix timestamp of last update.

    Raises:
        HTTPException 404: If ``job_id`` does not exist in ``JOBS``.
    """
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "process_log": job["process_log"],
            "result": job["result"],
            "error": job["error"],
            "updated_at": job["updated_at"],
        }


@app.post("/run/content")
def run_content(payload: ContentRequest) -> dict:
    """
    Runs the multi-LLM content generation pipeline synchronously.

    Request body (JSON):
        subject  (str, default "responsible use of AI agents in retail banking") :
                 The topic the content pipeline should write about.
        region   (str, default "US") : Geographic region for trend research.

    Returns:
        dict with keys:
            ``title``          (str)  — ``"Content Pipeline"``.
            ``process_log``    (str)  — captured console output.
            ``final_markdown`` (str)  — formatted Markdown with blog post
                                        and social posts.
            ``details``        (dict) — raw pipeline result dict.

    Raises:
        HTTPException 500: If the pipeline raises an unexpected exception.
    """
    try:
        result, process_log = _capture_sync(run_content_pipeline, subject=payload.subject, region=payload.region)
        final_markdown = _build_content_markdown(result)
        return {
            "title": "Content Pipeline",
            "process_log": process_log,
            "final_markdown": final_markdown,
            "details": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/run/flow")
async def run_flow() -> dict:
    """
    Runs the ``BankSalesFlow`` pipeline asynchronously and returns the
    formatted report.

    No request body — all lead data is defined inside ``BankSalesFlow``.

    Returns:
        dict with keys:
            ``title``          (str)  — ``"Sales Flow"``.
            ``process_log``    (str)  — captured console output.
            ``final_markdown`` (str)  — Markdown report with lead scores,
                                        high-priority leads, and emails.
            ``details``        (dict) — raw flow result dict including
                                        ``output_path`` and ``kickoff_result``.

    Raises:
        HTTPException 500: If the flow raises an unexpected exception.
    """
    try:
        result, process_log = await _capture_async(run_flow_kickoff)
        final_markdown = _build_sales_flow_markdown(result)
        return {
            "title": "Sales Flow",
            "process_log": process_log,
            "final_markdown": final_markdown,
            "details": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/reports")
def list_reports() -> dict[str, list[str]]:
    """
    Lists all files currently saved in the ``reports/`` directory.

    Recursively scans ``<project_root>/reports/`` and returns paths relative
    to the project root, sorted alphabetically.

    Returns:
        dict: ``{"reports": ["reports/file1.md", "reports/file2.json", ...]}``
        Returns ``{"reports": []}`` if the directory does not exist.
    """
    reports_dir = ROOT / "reports"
    if not reports_dir.exists():
        return {"reports": []}
    files = sorted(str(p.relative_to(ROOT)) for p in reports_dir.rglob("*") if p.is_file())
    return {"reports": files}
