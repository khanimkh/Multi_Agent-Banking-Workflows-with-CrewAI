from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml
from crewai import Agent, Crew, Process, Task

from .models import ContentOutput
from .tools import BankingTrendSignalTool


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = Path(__file__).parent
CONFIG_DIR = PACKAGE_DIR / "config"


def load_yaml(path: Path) -> dict[str, Any]:
    """
    Reads a YAML file from disk and returns its contents as a Python dict.

    Parameters:
        path (Path): Absolute or relative path to the ``.yaml`` file to load.

    Returns:
        dict[str, Any]: Parsed YAML contents. Raises ``FileNotFoundError`` if
        the file does not exist, or ``yaml.YAMLError`` if the file is malformed.
    """
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_model_overrides() -> dict[str, str]:
    """
    Reads environment variables to determine which LLM model each agent should
    use, falling back to a default model when a variable is not set.

    Environment variables checked (all optional):
        ``OPENAI_MODEL_NAME``  : Global default model for all agents.
                                 Defaults to ``"gpt-4o-mini"``.
        ``BANK_MARKET_LLM``    : Model for ``market_trends_agent``.
                                 Falls back to ``BANK_ALT_LLM``, then the default.
        ``BANK_STRATEGY_LLM``  : Model for ``audience_insights_agent``.
                                 Falls back to the default.
        ``BANK_CREATOR_LLM``   : Model for ``content_creator_agent``.
                                 Falls back to ``BANK_ALT_LLM``, then the default.
        ``BANK_QA_LLM``        : Model for ``quality_assurance_agent``.
                                 Falls back to the default.
        ``BANK_ALT_LLM``       : Shared alternative model used as a fallback
                                 for market and creator agents.

    Returns:
        dict[str, str]: Mapping of agent key name → resolved model string,
        covering all four content-pipeline agents.
    """
    default_model = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
    market_model = os.getenv("BANK_MARKET_LLM", os.getenv("BANK_ALT_LLM", default_model))
    strategy_model = os.getenv("BANK_STRATEGY_LLM", default_model)
    creator_model = os.getenv("BANK_CREATOR_LLM", os.getenv("BANK_ALT_LLM", default_model))
    qa_model = os.getenv("BANK_QA_LLM", default_model)

    return {
        "market_trends_agent": market_model,
        "audience_insights_agent": strategy_model,
        "content_creator_agent": creator_model,
        "quality_assurance_agent": qa_model,
    }


def build_agents(config: dict[str, Any], model_map: dict[str, str]) -> dict[str, Agent]:
    """
    Instantiates CrewAI ``Agent`` objects from a parsed YAML agent config,
    assigning each agent its designated LLM and any required tools.

    The special key ``market_trends_agent`` automatically receives a
    ``BankingTrendSignalTool`` instance. All other agents are created
    without tools.

    Parameters:
        config    (dict[str, Any])  : Parsed contents of a content agents YAML
                                      file. Each entry must contain ``role``,
                                      ``goal``, and ``backstory`` keys.
                                      Optional keys: ``allow_delegation``
                                      (bool, default False), ``verbose``
                                      (bool, default True).
        model_map (dict[str, str])  : Mapping of agent key name → LLM model
                                      string, typically produced by
                                      ``resolve_model_overrides()``. Used to
                                      set the ``llm`` parameter of each agent.

    Returns:
        dict[str, Agent]: Mapping of agent key name → instantiated ``Agent``.
    """
    agents: dict[str, Agent] = {}
    for key, cfg in config.items():
        agent_tools = []
        if key == "market_trends_agent":
            agent_tools = [BankingTrendSignalTool()]
        agents[key] = Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            allow_delegation=cfg.get("allow_delegation", False),
            verbose=cfg.get("verbose", True),
            llm=model_map.get(key),
            tools=agent_tools,
        )
    return agents


def write_outputs(result: Any) -> Path:
    """
    Extracts content from a CrewAI kickoff result and writes it to three
    output files under ``<project_root>/reports/``.

    If the result has a ``pydantic`` attribute (i.e. ``ContentOutput`` was
    used as the task's ``output_pydantic``), the structured data is used
    directly. Otherwise the result is converted to a string and treated as
    a plain blog post with no social posts.

    Parameters:
        result (Any): The raw value returned by ``crew.kickoff()``. Expected
                      to be a CrewAI result object that may carry a
                      ``pydantic`` field of type ``ContentOutput``.

    Side effects:
        Creates ``reports/`` directory if it does not exist, then writes:
            ``bank_blog_post.md``     — Long-form blog post in Markdown.
            ``bank_social_posts.md``  — Formatted Markdown with all social
                                        posts grouped by platform.
            ``bank_content_output.json`` — Full structured output as JSON.

    Returns:
        Path: The ``reports/`` directory path where files were written.
    """
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    social_md = reports_dir / "bank_social_posts.md"
    blog_md = reports_dir / "bank_blog_post.md"
    json_out = reports_dir / "bank_content_output.json"

    if hasattr(result, "pydantic") and result.pydantic:
        output = result.pydantic.model_dump()
    else:
        output = {"blog_post": str(result), "social_media_posts": []}

    blog_md.write_text(output.get("blog_post", ""), encoding="utf-8")

    social_lines: list[str] = ["# Bank Social Content", ""]
    for post in output.get("social_media_posts", []):
        social_lines.append(f"## {post.get('platform', 'Platform')}")
        social_lines.append(post.get("content", ""))
        social_lines.append("")
    social_md.write_text("\n".join(social_lines), encoding="utf-8")

    json_out.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return reports_dir


def parse_args() -> argparse.Namespace:
    """
    Parses command-line arguments for the content pipeline CLI.

    All flags are optional and have defaults so the pipeline can run
    immediately without any arguments.

    CLI flags:
        --subject  (str) : The topic the content pipeline should write about.
                           Default: ``"responsible use of AI agents in retail banking"``.
        --region   (str) : Geographic region that scopes market trend research
                           and audience analysis (e.g. ``"US"``, ``"UAE"``).
                           Default: ``"US"``.

    Returns:
        argparse.Namespace: Parsed argument object. Access values as
        ``args.subject`` and ``args.region``.
    """
    parser = argparse.ArgumentParser(
        description="Run project-5 style multi-LLM content pipeline for Bank Assistant."
    )
    parser.add_argument("--subject", default="responsible use of AI agents in retail banking")
    parser.add_argument("--region", default="US")
    return parser.parse_args()


def run_content_pipeline(subject: str, region: str) -> dict[str, Any]:
    """
    Orchestrates the full multi-LLM content generation pipeline end-to-end.

    Steps performed:
        1. Loads ``bank_content_agents.yaml`` and ``bank_content_tasks.yaml``.
        2. Resolves per-agent LLM model overrides from environment variables.
        3. Instantiates agents with ``build_agents()``.
        4. Builds four tasks in sequential order:
               ``monitor_banking_trends``        → ``market_trends_agent``
               ``analyze_audience_opportunities`` → ``audience_insights_agent``
               ``create_bank_content``           → ``content_creator_agent``
                   (uses ``ContentOutput`` as structured output model)
               ``quality_assurance``             → ``quality_assurance_agent``
        5. Runs the crew with ``Process.sequential``.
        6. Writes the results to disk via ``write_outputs()``.

    Parameters:
        subject (str) : The content topic. Substituted as ``{subject}`` in
                        task description and expected-output templates.
        region  (str) : Geographic region. Substituted as ``{region}`` in
                        task description and expected-output templates.

    Returns:
        dict with keys:
            ``reports_dir`` (str)        — path to the reports directory.
            ``model_map``   (dict)       — agent → LLM model routing used.
            ``raw_result``  (str)        — string repr of the crew kickoff result.
    """
    agents_cfg = load_yaml(CONFIG_DIR / "bank_content_agents.yaml")
    tasks_cfg = load_yaml(CONFIG_DIR / "bank_content_tasks.yaml")

    model_map = resolve_model_overrides()
    agents = build_agents(agents_cfg, model_map)

    task_agent_map = {
        "monitor_banking_trends": "market_trends_agent",
        "analyze_audience_opportunities": "audience_insights_agent",
        "create_bank_content": "content_creator_agent",
        "quality_assurance": "quality_assurance_agent",
    }

    tasks: list[Task] = []
    for task_name, cfg in tasks_cfg.items():
        task_kwargs: dict[str, Any] = {
            "description": cfg["description"].format(subject=subject, region=region),
            "expected_output": cfg["expected_output"].format(subject=subject, region=region),
            "agent": agents[task_agent_map[task_name]],
        }
        if task_name == "create_bank_content":
            task_kwargs["output_pydantic"] = ContentOutput
        tasks.append(Task(**task_kwargs))

    content_crew = Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    print("Running multi-LLM content pipeline...")
    print(f"Model routing: {model_map}")
    result = content_crew.kickoff(inputs={"subject": subject, "region": region})
    reports_dir = write_outputs(result)
    return {
        "reports_dir": str(reports_dir),
        "model_map": model_map,
        "raw_result": str(result),
    }


def main() -> None:
    """
    CLI entry point for the content pipeline.

    Parses command-line arguments via ``parse_args()``, passes them to
    ``run_content_pipeline()``, then prints the reports directory path
    to stdout.

    Invoked when running:
        python -m bank_assistant_crew.content_pipeline [--subject ...] [--region ...]

    No parameters — all input comes from ``sys.argv``.
    """
    args = parse_args()
    run_result = run_content_pipeline(subject=args.subject, region=args.region)
    print(f"Saved content outputs under: {run_result['reports_dir']}")


if __name__ == "__main__":
    main()
