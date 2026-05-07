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
    """
    Reads a YAML file from disk and returns its contents as a Python dict.

    Parameters:
        path (Path): Absolute or relative path to the ``.yaml`` file to load.

    Returns:
        dict[str, Any]: Parsed YAML contents. Raises ``FileNotFoundError`` if
        the file does not exist, or ``yaml.YAMLError`` if the file is malformed.
    """
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _build_agents(agent_config: dict[str, Any]) -> dict[str, Agent]:
    """
    Instantiates CrewAI ``Agent`` objects from a parsed YAML agent config.

    Each key in ``agent_config`` becomes the agent's lookup name. The special
    key ``lead_data_agent`` automatically receives all three data-fetching tools
    (``CustomerDataFetcherTool``, ``TransactionDataFetcherTool``,
    ``SupportTicketFetcherTool``). All other agents are created without tools.

    Parameters:
        agent_config (dict[str, Any]): Parsed contents of an agents YAML file.
            Each entry must contain ``role``, ``goal``, and ``backstory`` keys.
            Optional keys: ``allow_delegation`` (bool, default False),
            ``verbose`` (bool, default True).

    Returns:
        dict[str, Agent]: Mapping of agent key name → instantiated ``Agent``.
    """
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
    """
    Builds an ordered list of CrewAI ``Task`` objects from a parsed YAML task
    config, substituting runtime values into description templates.

    Parameters:
        task_config (dict[str, Any]): Parsed contents of a tasks YAML file.
            Each entry must contain ``description``, ``expected_output``, and
            ``agent`` (matching a key in ``agents``) fields. Both
            ``description`` and ``expected_output`` may contain
            ``{placeholder}`` variables that are filled from ``inputs``.
        agents (dict[str, Agent]): Agent lookup dict produced by
            ``_build_agents()``. The ``agent`` field in each task config
            must match a key here.
        inputs (dict[str, Any]): Runtime values used to format
            ``{placeholder}`` variables in task descriptions and
            expected-output strings.
        output_models (dict[str, type] | None): Optional mapping of task name
            → Pydantic model class. When a task name appears here its
            ``output_pydantic`` is set, enforcing structured output validation.
            Defaults to ``{}`` (no structured outputs).

    Returns:
        list[Task]: Ordered list of ``Task`` objects ready to pass to a
        ``Crew``. Order matches the iteration order of ``task_config``.
    """
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
    """
    Loads YAML config files, builds agents and tasks, and assembles a
    sequential ``Crew`` ready to be kicked off.

    This is the internal factory used by all public ``create_*`` functions.
    It combines ``load_yaml``, ``_build_agents``, and ``_build_tasks`` into a
    single call.

    Parameters:
        agent_file (Path)   : Path to the agents YAML file.
        task_file  (Path)   : Path to the tasks YAML file.
        inputs     (dict)   : Runtime values substituted into task description
                              and expected-output templates.
        output_models (dict[str, type] | None): Optional task-name → Pydantic
                              model mapping forwarded to ``_build_tasks``.
                              Defaults to ``None`` (no structured outputs).

    Returns:
        Crew: A configured ``Crew`` with ``process=Process.sequential`` and
        ``verbose=True``, ready to call ``.kickoff()`` or
        ``.kickoff_for_each()`` on.
    """
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
    """
    Creates a ``Crew`` configured to qualify and score a single bank lead.

    Uses ``bank_lead_qualification_agents.yaml`` and
    ``bank_lead_qualification_tasks.yaml``. The ``lead_scoring_and_validation``
    task is configured with ``LeadQualificationOutput`` as its Pydantic output
    model, so the crew returns a validated structured result.

    Parameters:
        lead_data (dict[str, Any]): A dict representing one lead's pipeline
            batch payload. Passed to task templates as ``{lead_data}``.
            Typically contains the raw lead dict produced by
            ``BankSalesFlow.fetch_leads()``.

    Returns:
        Crew: A ready-to-kickoff crew that scores the lead and validates the
        result against ``LeadQualificationOutput``.
    """
    return _build_crew(
        CONFIG_DIR / "bank_lead_qualification_agents.yaml",
        CONFIG_DIR / "bank_lead_qualification_tasks.yaml",
        {"lead_data": lead_data},
        {"lead_scoring_and_validation": LeadQualificationOutput},
    )


def create_bank_email_engagement_crew(payload: dict[str, Any]) -> Crew:
    """
    Creates a ``Crew`` configured to write and optimise a personalised
    engagement email for a single qualified lead.

    Uses ``bank_email_engagement_agents.yaml`` and
    ``bank_email_engagement_tasks.yaml``. The ``engagement_optimization``
    task is configured with ``EmailEngagementOutput`` as its Pydantic output
    model.

    Parameters:
        payload (dict[str, Any]): Lead context for email personalisation.
            Expected keys (all optional, fall back to ``"Not provided"``):
                ``personal_info`` (str) — name and job title of the lead.
                ``company_info``  (str) — segment and region of the lead.
                ``lead_score``    (int|str) — numeric lead quality score.

    Returns:
        Crew: A ready-to-kickoff crew that generates a subject line, email
        body, and primary CTA validated against ``EmailEngagementOutput``.
    """
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
    """
    Builds and immediately runs a crew from the given YAML files, printing a
    titled separator to stdout before execution.

    Used by ``main.py`` to execute named workflows (e.g. Customer Advisory,
    Risk and Compliance) in sequence without needing structured output models.

    Parameters:
        agent_file (Path)      : Path to the agents YAML config file.
        task_file  (Path)      : Path to the tasks YAML config file.
        inputs     (dict)      : Runtime values substituted into task
                                 description and expected-output templates
                                 (e.g. ``customer_name``, ``region``,
                                 ``risk_level``).
        title      (str)       : Human-readable workflow name printed as a
                                 banner before the crew runs
                                 (e.g. ``"Workflow 1: Customer Advisory"``).

    Returns:
        str: String representation of the crew's final kickoff result,
        suitable for writing directly to a Markdown report.
    """
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
