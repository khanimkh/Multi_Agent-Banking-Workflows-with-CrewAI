from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class LeadQualificationOutput(BaseModel):
    customer_name: str = Field(..., description="Lead/customer name.")
    lead_score: int = Field(..., ge=0, le=100, description="Validated lead score between 0 and 100.")
    fit_score: int = Field(..., ge=0, le=10, description="Qualitative fit score between 0 and 10.")
    recommended_path: str = Field(..., description="Recommended service or product path.")
    risk_notes: str = Field(..., description="Risk or caveat notes relevant to this lead.")


class EmailEngagementOutput(BaseModel):
    subject_line: str = Field(..., description="Suggested email subject line.")
    email_body: str = Field(..., description="Final optimized email body.")
    primary_cta: str = Field(..., description="Primary customer call to action.")


class RiskComplianceOutput(BaseModel):
    risk_level: str = Field(..., description="Final risk level classification.")
    top_risks: List[str] = Field(..., description="Top identified risk items.")
    controls: List[str] = Field(..., description="Recommended controls and mitigations.")
    escalation_required: bool = Field(..., description="Whether escalation is required.")


class SocialMediaPost(BaseModel):
    platform: str = Field(..., description="Social media platform, such as LinkedIn or X.")
    content: str = Field(..., description="Post content with concise message and CTA.")


class ContentOutput(BaseModel):
    blog_post: str = Field(..., description="Long-form blog post in markdown.")
    social_media_posts: List[SocialMediaPost] = Field(
        ..., description="List of social media posts derived from the same topic."
    )
