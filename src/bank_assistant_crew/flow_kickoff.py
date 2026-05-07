from __future__ import annotations

import asyncio
import inspect
from typing import Any

from .sales_flow import BankSalesFlow


async def run_flow_kickoff() -> dict[str, Any]:
    """
    Instantiates and runs the full ``BankSalesFlow`` pipeline, then persists
    the results to disk.

    Steps performed:
        1. Creates a new ``BankSalesFlow`` instance.
        2. Calls ``flow.kickoff()`` to execute every step in the flow
           (fetch_leads → score_leads → filter_leads / store_leads_score
           → write_email → send_email).
        3. Awaits the result if the flow returns a coroutine
           (supports both sync and async CrewAI versions).
        4. Calls ``flow.save_run_summary()`` to write the JSON output file.

    No parameters — all lead data and configuration come from inside
    ``BankSalesFlow`` itself.

    Returns:
        dict with keys:
            ``output_path``    (str) — absolute path to the saved JSON summary.
            ``kickoff_result`` (str) — string representation of the raw
                                       CrewAI flow result object.
    """
    flow = BankSalesFlow()
    kickoff_result = flow.kickoff()
    if inspect.isawaitable(kickoff_result):
        kickoff_result = await kickoff_result

    output_path = flow.save_run_summary()
    return {
        "output_path": str(output_path),
        "kickoff_result": str(kickoff_result),
    }


async def _run_flow() -> None:
    """
    Awaits ``run_flow_kickoff()`` and prints a human-readable summary to stdout.

    This is an internal helper used only by ``main()`` to bridge the async
    flow execution with the synchronous ``asyncio.run()`` entry point.
    It is not intended to be called directly from outside this module.

    No parameters.

    Side effects:
        Prints three lines to stdout:
            - Completion confirmation message.
            - Path to the saved output file.
            - String representation of the kickoff result.
    """
    result = await run_flow_kickoff()
    print("Flow kickoff completed.")
    print(f"Saved flow output to: {result['output_path']}")
    print(f"Kickoff result: {result['kickoff_result']}")


def main() -> None:
    """
    Synchronous CLI entry point for the sales flow.

    Wraps the async ``_run_flow()`` coroutine with ``asyncio.run()`` so the
    flow can be launched from a plain terminal command or script without
    any external async runner.

    Invoked when running:
        python -m bank_assistant_crew.flow_kickoff

    No parameters — all configuration is embedded in ``BankSalesFlow``.
    """
    asyncio.run(_run_flow())


if __name__ == "__main__":
    main()
