from __future__ import annotations

import argparse
import textwrap
from typing import Any

from .crew import CONFIG_DIR, ROOT, run_workflow


def parse_args() -> argparse.Namespace:
    """
    Parses command-line arguments for the Bank Assistant CLI.

    No positional arguments are required — all flags have sensible defaults
    so the tool can be run without any arguments for a quick demo.

    CLI flags:
        --customer-name   (str) : Full name of the customer to analyse.
                                  Default: "Alex Morgan".
        --customer-goal   (str) : The customer's primary financial objective
                                  (e.g. "reduce monthly credit card debt",
                                  "home loan pre-approval").
                                  Default: "reduce monthly credit card debt".
        --region          (str) : Customer's geographic region (e.g. "US", "UAE").
                                  Used by agents to tailor product recommendations
                                  and compliance checks.
                                  Default: "US".
        --risk-level      (str) : Initial risk classification passed to the
                                  risk-and-compliance crew
                                  (e.g. "low", "medium", "high").
                                  Default: "medium".

    Returns:
        argparse.Namespace: Parsed argument object. Access values as
        ``args.customer_name``, ``args.customer_goal``, ``args.region``,
        ``args.risk_level``.
    """
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
    """
    Executes both primary CrewAI workflows sequentially and saves a combined
    Markdown report to disk.

    Workflow 1 — Customer Advisory and Service:
        Uses ``agents.yaml`` + ``tasks.yaml``. Agents analyse the customer's
        goal and region, then produce personalised product recommendations
        and an engagement plan.

    Workflow 2 — Risk and Compliance Validation:
        Uses ``risk_compliance_agents.yaml`` + ``risk_compliance_tasks.yaml``.
        Agents review the same customer context against compliance rules and
        produce a risk classification with recommended controls.

    Both workflows receive the same ``inputs`` dict so agents share a
    consistent view of the customer.

    Parameters:
        customer_name  (str) : Full name of the customer being processed.
        customer_goal  (str) : The customer's stated financial objective.
        region         (str) : Geographic region of the customer
                               (affects regulatory and product logic).
        risk_level     (str) : Initial risk classification hint passed to
                               the compliance crew.

    Side effects:
        Writes a consolidated Markdown report to
        ``<project_root>/reports/bank_assistant_summary.md``.

    Returns:
        dict with keys:
            ``advisory_result`` (str)  — raw output from Workflow 1.
            ``risk_result``     (str)  — raw output from Workflow 2.
            ``report_path``     (str)  — absolute path to the saved report file.
    """
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
    """
    CLI entry point for the Bank Assistant.

    Parses command-line arguments via ``parse_args()``, passes them to
    ``run_primary_workflows()``, then prints the path of the saved report
    to stdout.

    Invoked when running:
        python -m bank_assistant_crew.main [flags]

    No parameters — all input comes from ``sys.argv``.
    """
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
