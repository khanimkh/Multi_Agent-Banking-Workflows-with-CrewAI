from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from crewai.tools import BaseTool


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"


class CustomerDataFetcherTool(BaseTool):
    """
    CrewAI tool that looks up customer records from the local
    ``data/customers.csv`` file.

    Assigned to ``lead_data_agent`` so the agent can retrieve real customer
    profile data during lead qualification and advisory workflows.
    """
    name: str = "Customer Data Fetcher"
    description: str = "Fetch customer records by customer_id or partial full_name from local CSV data."

    def _run(self, customer_id: str = "", full_name: str = "") -> str:
        """
        Queries ``customers.csv`` and returns matching rows as a JSON string.

        Lookup priority:
        1. If ``customer_id`` is provided, returns rows where
           ``customer_id`` matches exactly (case-insensitive).
        2. Else if ``full_name`` is provided, returns rows where
           ``full_name`` contains the search string (case-insensitive,
           partial match allowed).
        3. If neither is provided, returns all customer records.

        Parameters:
            customer_id (str) : Exact customer ID to look up.
                                Defaults to ``""`` (not used).
            full_name   (str) : Partial or full name to search for.
                                Defaults to ``""`` (not used).

        Returns:
            str: JSON array of matching customer record dicts,
            pretty-printed with 2-space indentation.
        """
        customers = pd.read_csv(DATA_DIR / "customers.csv")

        if customer_id:
            rows = customers[customers["customer_id"].astype(str).str.lower() == customer_id.lower()]
        elif full_name:
            rows = customers[customers["full_name"].astype(str).str.contains(full_name, case=False, na=False)]
        else:
            rows = customers

        return json.dumps(rows.to_dict(orient="records"), indent=2)


class TransactionDataFetcherTool(BaseTool):
    """
    CrewAI tool that retrieves transaction history for a specific customer
    from the local ``data/transactions.csv`` file.

    Assigned to ``lead_data_agent`` to give agents visibility into a
    customer's spending and payment behaviour during analysis.
    """
    name: str = "Transaction Data Fetcher"
    description: str = "Fetch transaction records by customer_id from local CSV data."

    def _run(self, customer_id: str) -> str:
        """
        Queries ``transactions.csv`` and returns all rows matching the given
        customer ID as a JSON string.

        Parameters:
            customer_id (str) : The customer ID to filter by
                                (case-insensitive exact match).

        Returns:
            str: JSON array of matching transaction record dicts,
            pretty-printed with 2-space indentation. Returns an empty
            array ``[]`` if no matching rows are found.
        """
        txns = pd.read_csv(DATA_DIR / "transactions.csv")
        rows = txns[txns["customer_id"].astype(str).str.lower() == customer_id.lower()]
        return json.dumps(rows.to_dict(orient="records"), indent=2)


class SupportTicketFetcherTool(BaseTool):
    """
    CrewAI tool that retrieves open or historical support tickets for a
    specific customer from the local ``data/support_tickets.csv`` file.

    Assigned to ``lead_data_agent`` to provide agents with context about
    a customer's past issues and service interactions.
    """
    name: str = "Support Ticket Fetcher"
    description: str = "Fetch customer support tickets by customer_id from local CSV data."

    def _run(self, customer_id: str) -> str:
        """
        Queries ``support_tickets.csv`` and returns all rows matching the
        given customer ID as a JSON string.

        Parameters:
            customer_id (str) : The customer ID to filter by
                                (case-insensitive exact match).

        Returns:
            str: JSON array of matching support ticket record dicts,
            pretty-printed with 2-space indentation. Returns an empty
            array ``[]`` if no matching rows are found.
        """
        tickets = pd.read_csv(DATA_DIR / "support_tickets.csv")
        rows = tickets[tickets["customer_id"].astype(str).str.lower() == customer_id.lower()]
        return json.dumps(rows.to_dict(orient="records"), indent=2)


class BankingTrendSignalTool(BaseTool):
    """
    CrewAI tool that generates curated banking trend signals for a given
    topic and geographic region.

    Assigned to ``market_trends_agent`` in the content pipeline to seed
    market research before content is drafted. Signals are hardcoded per
    region and supplemented with topic-specific additions for ``mortgage``
    and ``credit`` subjects.
    """
    name: str = "Banking Trend Signal Tool"
    description: str = "Provide trend signals for a topic and region to seed content analysis."

    def _run(self, subject: str, region: str = "US") -> str:
        """
        Returns a JSON payload of trend signals relevant to ``subject``
        in the specified ``region``.

        Regional signal sets are available for ``"US"``, ``"UAE"``, and
        ``"UK"``. Any unrecognised region falls back to the US signal set.
        Additional topic-specific signals are appended when ``subject``
        contains the keywords ``"mortgage"`` or ``"credit"``.

        Parameters:
            subject (str)        : The content or research topic
                                   (e.g. ``"AI agents in retail banking"``,
                                   ``"mortgage affordability"``).
                                   Used for keyword-based signal injection.
            region  (str)        : Target geographic region
                                   (``"US"``, ``"UAE"``, or ``"UK"``).
                                   Case-insensitive. Defaults to ``"US"``.

        Returns:
            str: JSON object with keys:
                ``subject``  (str)       — echoed back from input.
                ``region``   (str)       — echoed back from input.
                ``signals``  (list[str]) — list of trend signal strings
                                           for the agent to reason over.
            Pretty-printed with 2-space indentation.
        """
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
