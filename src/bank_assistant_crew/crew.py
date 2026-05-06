from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from crewai import Agent, Crew, Process, Task

from .models import EmailEngagementOutput, LeadQualificationOutput
from .tools import CustomerDataFetcherTool, SupportTicketFetcherTool, TransactionDataFetcherTool


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = Path(__file__).parent
CONFIG_DIR = PACKAGE_DIR / "config"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _build_agents(agent_config: dict[str, Any]) -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    for key, cfg in agent_config.items():
        agent_tools = []
        if key == "lead_data_agent":
            agent_tools = [CustomerDataFetcherTool(), TransactionDataFetcherTool(), SupportTicketFetcherTool()]
        agents[key] = Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            allow_delegation=cfg.get("allow_delegation", False),
            verbose=cfg.get("verbose", True),
            tools=agent_tools,
        )
    return agents


def _build_tasks(
    task_config: dict[str, Any],
    agents: dict[str, Agent],
    inputs: dict[str, Any],
    output_models: dict[str, type] | None = None,
) -> list[Task]:
    tasks: list[Task] = []
    output_models = output_models or {}
    for task_name, cfg in task_config.items():
        task_kwargs: dict[str, Any] = {
            "description": cfg["description"].format(**inputs),
            "expected_output": cfg["expected_output"].format(**inputs),
            "agent": agents[cfg["agent"]],
        }
        if task_name in output_models:
            task_kwargs["output_pydantic"] = output_models[task_name]
        tasks.append(Task(**task_kwargs))
    return tasks


def _build_crew(
    agent_file: Path,
    task_file: Path,
    inputs: dict[str, Any],
    output_models: dict[str, type] | None = None,
) -> Crew:
    agent_cfg = load_yaml(agent_file)
    task_cfg = load_yaml(task_file)
    agents = _build_agents(agent_cfg)
    tasks = _build_tasks(task_cfg, agents, inputs, output_models)

    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )


def create_bank_lead_qualification_crew(lead_data: dict[str, Any]) -> Crew:
    return _build_crew(
        CONFIG_DIR / "bank_lead_qualification_agents.yaml",
        CONFIG_DIR / "bank_lead_qualification_tasks.yaml",
        {"lead_data": lead_data},
        {"lead_scoring_and_validation": LeadQualificationOutput},
    )


def create_bank_email_engagement_crew(payload: dict[str, Any]) -> Crew:
    defaults = {
        "personal_info": payload.get("personal_info", "Not provided"),
        "company_info": payload.get("company_info", "Not provided"),
        "lead_score": payload.get("lead_score", "Not provided"),
    }
    return _build_crew(
        CONFIG_DIR / "bank_email_engagement_agents.yaml",
        CONFIG_DIR / "bank_email_engagement_tasks.yaml",
        defaults,
        {"engagement_optimization": EmailEngagementOutput},
    )


def run_workflow(agent_file: Path, task_file: Path, inputs: dict[str, Any], title: str) -> str:
    agent_cfg = load_yaml(agent_file)
    task_cfg = load_yaml(task_file)

    agents = _build_agents(agent_cfg)
    tasks = _build_tasks(task_cfg, agents, inputs)

    crew = Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")
    result = crew.kickoff()
    return str(result)
