from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crewai import Flow
from crewai.flow.flow import listen, start

from .crew import create_bank_email_engagement_crew, create_bank_lead_qualification_crew


ROOT = Path(__file__).resolve().parents[2]


class BankSalesFlow(Flow):
    @start()
    def fetch_leads(self) -> list[dict[str, Any]]:
        """
        Entry point of the flow. Produces the initial list of leads to process.

        No parameters — this method is called automatically by CrewAI when the
        flow is kicked off.

        Returns:
            list[dict]: Each element is a dict with a single key ``lead_data``
            whose value contains the lead's personal and contact details:
            ``name``, ``job_title``, ``segment``, ``email``, ``goal``,
            ``preferred_channel``, and ``region``.
        """
        return [
            {
                "lead_data": {
                    "name": "Alex Morgan",
                    "job_title": "Operations Manager",
                    "segment": "Mass Affluent",
                    "email": "alex.morgan@example.com",
                    "goal": "reduce monthly credit card debt",
                    "preferred_channel": "Mobile",
                    "region": "US",
                }
            },
            {
                "lead_data": {
                    "name": "Leila Haddad",
                    "job_title": "Finance Lead",
                    "segment": "Emerging Affluent",
                    "email": "leila.haddad@example.com",
                    "goal": "pre-approval for home loan",
                    "preferred_channel": "WhatsApp",
                    "region": "UAE",
                }
            },
        ]

    @listen(fetch_leads)
    def score_leads(self, leads: list[dict[str, Any]]) -> list[Any]:
        """
        Scores each lead using the lead-qualification crew.

        Triggered automatically after ``fetch_leads`` completes.

        Parameters:
            leads (list[dict]): The raw lead list produced by ``fetch_leads``.
                Each element is expected to have a ``lead_data`` key.

        Side effects:
            - Stores the original lead metadata in ``self.state["source_leads"]``
              so later steps can backfill fields that the scoring crew may drop.
            - Stores raw crew results in ``self.state["score_crews_results"]``.

        Returns:
            list: Raw CrewAI kickoff results — one result object per lead.
        """
        # Keep original lead metadata so report fields remain available after scoring.
        self.state["source_leads"] = [
            lead.get("lead_data", {}) if isinstance(lead, dict) else {} for lead in leads
        ]
        lead_scoring_crew = create_bank_lead_qualification_crew({"pipeline_batch": leads})
        scores = lead_scoring_crew.kickoff_for_each(leads)
        self.state["score_crews_results"] = scores
        return scores

    @listen(score_leads)
    def store_leads_score(self, scores: list[Any]) -> list[Any]:
        """
        Normalizes and persists scored lead data to flow state.

        Triggered automatically after ``score_leads`` completes.
        Runs in parallel with ``filter_leads``.

        Parameters:
            scores (list): Raw crew result objects returned by ``score_leads``.

        Side effects:
            Writes the normalized, flat lead dicts to
            ``self.state["scored_leads"]`` so ``save_run_summary`` can include
            them in the final output file.

        Returns:
            list: The same ``scores`` list, passed through unchanged so other
            listeners can also receive it.
        """
        source_leads = self.state.get("source_leads", [])
        self.state["scored_leads"] = [
            self._normalize_score(score=s, source_lead=source_leads[index] if index < len(source_leads) else {})
            for index, s in enumerate(scores)
        ]
        return scores

    @listen(score_leads)
    def filter_leads(self, scores: list[Any]) -> list[dict[str, Any]]:
        """
        Filters scored leads and keeps only those above the priority threshold.

        Triggered automatically after ``score_leads`` completes.
        Runs in parallel with ``store_leads_score``.

        Parameters:
            scores (list): Raw crew result objects returned by ``score_leads``.

        Side effects:
            Writes the filtered list to ``self.state["high_priority_leads"]``.

        Returns:
            list[dict]: Normalized lead dicts where ``lead_score >= 70``.
            These are forwarded to ``write_email``.
        """
        source_leads = self.state.get("source_leads", [])
        normalized = [
            self._normalize_score(score=score, source_lead=source_leads[index] if index < len(source_leads) else {})
            for index, score in enumerate(scores)
        ]
        high_priority = [item for item in normalized if item.get("lead_score", 75) >= 70]
        self.state["high_priority_leads"] = high_priority
        return high_priority

    @listen(filter_leads)
    def write_email(self, qualified_leads: list[dict[str, Any]]) -> list[Any]:
        """
        Generates a personalised engagement email for each high-priority lead.

        Triggered automatically after ``filter_leads`` completes.

        Parameters:
            qualified_leads (list[dict]): Normalized lead dicts from
                ``filter_leads``. Expected keys per lead: ``name``,
                ``job_title``, ``segment``, ``region``, ``lead_score``.

        Returns:
            list: Raw CrewAI kickoff results — one email result per lead.
            Returns an empty list if ``qualified_leads`` is empty.
        """
        if not qualified_leads:
            return []

        email_payload = []
        for lead in qualified_leads:
            lead_name = lead.get("name", "Customer")
            email_payload.append(
                {
                    "personal_info": f"Name: {lead_name}; Job: {lead.get('job_title', 'N/A')}",
                    "company_info": f"Segment: {lead.get('segment', 'N/A')}; Region: {lead.get('region', 'N/A')}",
                    "lead_score": lead.get("lead_score", 75),
                }
            )

        email_writing_crew = create_bank_email_engagement_crew(email_payload[0])
        return email_writing_crew.kickoff_for_each(email_payload)

    @listen(write_email)
    def send_email(self, emails: list[Any]) -> list[Any]:
        """
        Finalizes and stores the generated emails in flow state.

        Triggered automatically after ``write_email`` completes.
        In this implementation the emails are normalized and saved rather than
        actually dispatched — extend this method to integrate a real mail API.

        Parameters:
            emails (list): Raw crew result objects returned by ``write_email``.

        Side effects:
            Writes the normalized email records to ``self.state["emails"]``
            so ``save_run_summary`` can include them in the output file.

        Returns:
            list: The same ``emails`` list, passed through unchanged.
        """
        self.state["emails"] = [self._normalize_result(e) for e in emails]
        return emails

    def save_run_summary(self, output_file: Path | None = None) -> Path:
        """
        Serializes the complete flow results to a JSON file on disk.

        Must be called explicitly after the flow finishes — it is not wired
        into the ``@listen`` chain.

        Parameters:
            output_file (Path | None): Optional path for the output JSON file.
                Defaults to ``<project_root>/reports/bank_sales_flow_output.json``.

        Returns:
            Path: The absolute path to the file that was written.

        Output JSON keys:
            - ``scored_leads``      — all leads with their scores
            - ``high_priority_leads`` — leads that passed the score threshold
            - ``emails``            — generated email records
        """
        path = output_file or ROOT / "reports" / "bank_sales_flow_output.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "scored_leads": self.state.get("scored_leads", []),
            "high_priority_leads": self.state.get("high_priority_leads", []),
            "emails": self.state.get("emails", []),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def _normalize_result(value: Any) -> Any:
        """
        Converts a CrewAI result object into a plain Python type for storage.

        Handles three cases:
        1. Object has a ``to_dict()`` method — call it and return the dict.
        2. Object has a ``raw`` attribute — return ``{"raw": str(value.raw)}``.
        3. Anything else — returned as-is.

        Parameters:
            value (Any): A CrewAI kickoff result, a dict, a string, or any
                other value produced by a crew step.

        Returns:
            Any: A JSON-serializable representation of ``value``.
        """
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if hasattr(value, "raw"):
            return {"raw": str(value.raw)}
        return value

    def _normalize_score(self, score: Any, source_lead: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Flattens a lead scoring result into a single dict, backfilling any
        fields that the crew may have dropped from the original lead record.

        Parameters:
            score (Any): A raw crew result for one lead — may be a CrewAI
                result object, a dict with a ``lead_data`` sub-key, or a
                plain string.
            source_lead (dict | None): The original lead dict from
                ``fetch_leads`` (i.e. the inner ``lead_data`` dict). Used to
                restore fields like ``name``, ``region``, ``goal``, etc. that
                the scoring crew might not echo back. Defaults to ``{}``.

        Returns:
            dict: A flat dict containing all available lead fields plus
            ``lead_score`` (int, defaults to 75 if absent or unparseable).
            If normalisation fails entirely a fallback dict is returned that
            includes the source fields and ``"raw"`` with the string repr.
        """
        source_lead = source_lead or {}
        normalized = self._normalize_result(score)
        if isinstance(normalized, dict):
            lead_data = normalized.get("lead_data", {}) if isinstance(normalized.get("lead_data"), dict) else {}
            flat = {**lead_data}

            # Some structured outputs return customer_name instead of name.
            if "name" not in flat and isinstance(normalized.get("customer_name"), str):
                flat["name"] = normalized["customer_name"]

            # Backfill missing context fields from the original source lead.
            for key in ["name", "region", "goal", "segment", "job_title", "email", "preferred_channel"]:
                if key not in flat and key in source_lead:
                    flat[key] = source_lead[key]

            if "lead_score" in normalized:
                try:
                    flat["lead_score"] = int(normalized["lead_score"])
                except Exception:
                    flat["lead_score"] = 75
            else:
                flat["lead_score"] = 75
            return flat
        fallback = {**source_lead}
        fallback["lead_score"] = 75
        fallback["raw"] = str(normalized)
        return fallback
