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
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


async def _capture_async(func, *args, **kwargs):
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = await func(*args, **kwargs)
    return result, buffer.getvalue()


def _read_if_exists(path_str: str) -> str:
    path = Path(path_str)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _json_to_markdown(value: dict | list | str) -> str:
    if isinstance(value, str):
        return value
    return "```json\n" + json.dumps(value, indent=2) + "\n```"


def _extract_literal_field(text: str, field_name: str, stop_fields: list[str]) -> object | None:
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
    posts: list[dict[str, str]] = []
    for match in re.finditer(r"^-\s*\*\*(.+?)\*\*:\s*(.+)$", text, flags=re.MULTILINE):
        posts.append({"platform": match.group(1).strip(), "content": match.group(2).strip()})
    return posts


def _parse_social_posts_md(text: str) -> list[dict[str, str]]:
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
    def __init__(self, job_id: str):
        self.job_id = job_id

    def write(self, text: str) -> int:
        if not text:
            return 0
        with JOBS_LOCK:
            job = JOBS.get(self.job_id)
            if job is not None:
                job["process_log"] += text
                job["updated_at"] = time.time()
        return len(text)

    def flush(self) -> None:
        return None


def _build_primary_response(result: dict, process_log: str) -> dict:
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
    return {"status": "ok"}


@app.get("/")
def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/app.js")
def serve_frontend_js() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")


@app.get("/style.css")
def serve_frontend_css() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "style.css", media_type="text/css")


@app.post("/run/primary")
def run_primary(payload: PrimaryRequest) -> dict:
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
    try:
        job_id = _start_primary_job(payload)
        return {"job_id": job_id, "status": "queued"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
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
    reports_dir = ROOT / "reports"
    if not reports_dir.exists():
        return {"reports": []}
    files = sorted(str(p.relative_to(ROOT)) for p in reports_dir.rglob("*") if p.is_file())
    return {"reports": files}
