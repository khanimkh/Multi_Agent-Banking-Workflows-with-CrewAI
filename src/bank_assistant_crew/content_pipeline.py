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
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_model_overrides() -> dict[str, str]:
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
    parser = argparse.ArgumentParser(
        description="Run project-5 style multi-LLM content pipeline for Bank Assistant."
    )
    parser.add_argument("--subject", default="responsible use of AI agents in retail banking")
    parser.add_argument("--region", default="US")
    return parser.parse_args()


def run_content_pipeline(subject: str, region: str) -> dict[str, Any]:
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
    args = parse_args()
    run_result = run_content_pipeline(subject=args.subject, region=args.region)
    print(f"Saved content outputs under: {run_result['reports_dir']}")


if __name__ == "__main__":
    main()
