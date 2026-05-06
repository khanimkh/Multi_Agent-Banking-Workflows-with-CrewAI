from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from crewai.tools import BaseTool


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"


class CustomerDataFetcherTool(BaseTool):
    name: str = "Customer Data Fetcher"
    description: str = "Fetch customer records by customer_id or partial full_name from local CSV data."

    def _run(self, customer_id: str = "", full_name: str = "") -> str:
        customers = pd.read_csv(DATA_DIR / "customers.csv")

        if customer_id:
            rows = customers[customers["customer_id"].astype(str).str.lower() == customer_id.lower()]
        elif full_name:
            rows = customers[customers["full_name"].astype(str).str.contains(full_name, case=False, na=False)]
        else:
            rows = customers

        return json.dumps(rows.to_dict(orient="records"), indent=2)


class TransactionDataFetcherTool(BaseTool):
    name: str = "Transaction Data Fetcher"
    description: str = "Fetch transaction records by customer_id from local CSV data."

    def _run(self, customer_id: str) -> str:
        txns = pd.read_csv(DATA_DIR / "transactions.csv")
        rows = txns[txns["customer_id"].astype(str).str.lower() == customer_id.lower()]
        return json.dumps(rows.to_dict(orient="records"), indent=2)


class SupportTicketFetcherTool(BaseTool):
    name: str = "Support Ticket Fetcher"
    description: str = "Fetch customer support tickets by customer_id from local CSV data."

    def _run(self, customer_id: str) -> str:
        tickets = pd.read_csv(DATA_DIR / "support_tickets.csv")
        rows = tickets[tickets["customer_id"].astype(str).str.lower() == customer_id.lower()]
        return json.dumps(rows.to_dict(orient="records"), indent=2)


class BankingTrendSignalTool(BaseTool):
    name: str = "Banking Trend Signal Tool"
    description: str = "Provide trend signals for a topic and region to seed content analysis."

    def _run(self, subject: str, region: str = "US") -> str:
        subject_l = subject.lower()
        regional_signals: dict[str, list[str]] = {
            "US": [
                "Deposit competition is increasing with high-yield digital savings products.",
                "Credit card delinquency pressure remains elevated in some retail segments.",
                "Banks are expanding agent-assisted customer support automation.",
            ],
            "UAE": [
                "Strong digital onboarding growth in retail banking.",
                "SME lending digitization and faster approval journeys are expanding.",
                "Customer demand for multilingual digital service continues to rise.",
            ],
            "UK": [
                "Open-banking powered financial management experiences are expanding.",
                "Cost-of-living pressure keeps savings and debt-optimization content relevant.",
                "Regulated AI usage in financial communication is under tighter scrutiny.",
            ],
        }

        signals = regional_signals.get(region.upper(), regional_signals["US"])
        if "mortgage" in subject_l:
            signals.append("Mortgage affordability messaging should include rate sensitivity scenarios.")
        if "credit" in subject_l:
            signals.append("Responsible credit education content should include repayment planning guidance.")

        payload: dict[str, Any] = {
            "subject": subject,
            "region": region,
            "signals": signals,
        }
        return json.dumps(payload, indent=2)
