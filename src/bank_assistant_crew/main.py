from __future__ import annotations

import argparse
import textwrap
from typing import Any

from .crew import CONFIG_DIR, ROOT, run_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Multi-AI Agent Bank Assistant workflows using CrewAI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Example:
              python -m bank_assistant_crew.main --customer-name "Fatemeh Rahimi" --customer-goal "home loan pre-approval" --region "UAE"
            """
        ),
    )
    parser.add_argument("--customer-name", default="Alex Morgan")
    parser.add_argument("--customer-goal", default="reduce monthly credit card debt")
    parser.add_argument("--region", default="US")
    parser.add_argument("--risk-level", default="medium")
    return parser.parse_args()


def run_primary_workflows(
    customer_name: str,
    customer_goal: str,
    region: str,
    risk_level: str,
) -> dict[str, Any]:
    inputs = {
        "customer_name": customer_name,
        "customer_goal": customer_goal,
        "region": region,
        "risk_level": risk_level,
    }

    advisory_result = run_workflow(
        CONFIG_DIR / "agents.yaml",
        CONFIG_DIR / "tasks.yaml",
        inputs,
        "Workflow 1: Customer Advisory and Service",
    )

    risk_result = run_workflow(
        CONFIG_DIR / "risk_compliance_agents.yaml",
        CONFIG_DIR / "risk_compliance_tasks.yaml",
        inputs,
        "Workflow 2: Risk and Compliance Validation",
    )

    output = ROOT / "reports" / "bank_assistant_summary.md"
    output.parent.mkdir(exist_ok=True)
    output.write_text(
        "# Bank Assistant Multi-Agent Run\n\n"
        "## Advisory and Service Workflow\n\n"
        f"{advisory_result}\n\n"
        "## Risk and Compliance Workflow\n\n"
        f"{risk_result}\n",
        encoding="utf-8",
    )

    return {
        "advisory_result": advisory_result,
        "risk_result": risk_result,
        "report_path": str(output),
    }


def main() -> None:
    args = parse_args()
    result = run_primary_workflows(
        customer_name=args.customer_name,
        customer_goal=args.customer_goal,
        region=args.region,
        risk_level=args.risk_level,
    )
    print(f"\nSaved consolidated output to: {result['report_path']}")


if __name__ == "__main__":
    main()
