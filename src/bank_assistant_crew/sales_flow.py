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
        source_leads = self.state.get("source_leads", [])
        self.state["scored_leads"] = [
            self._normalize_score(score=s, source_lead=source_leads[index] if index < len(source_leads) else {})
            for index, s in enumerate(scores)
        ]
        return scores

    @listen(score_leads)
    def filter_leads(self, scores: list[Any]) -> list[dict[str, Any]]:
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
        self.state["emails"] = [self._normalize_result(e) for e in emails]
        return emails

    def save_run_summary(self, output_file: Path | None = None) -> Path:
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
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if hasattr(value, "raw"):
            return {"raw": str(value.raw)}
        return value

    def _normalize_score(self, score: Any, source_lead: dict[str, Any] | None = None) -> dict[str, Any]:
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
