from __future__ import annotations

import asyncio
import inspect
from typing import Any

from .sales_flow import BankSalesFlow


async def run_flow_kickoff() -> dict[str, Any]:
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
    result = await run_flow_kickoff()
    print("Flow kickoff completed.")
    print(f"Saved flow output to: {result['output_path']}")
    print(f"Kickoff result: {result['kickoff_result']}")


def main() -> None:
    asyncio.run(_run_flow())


if __name__ == "__main__":
    main()
