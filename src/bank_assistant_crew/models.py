from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class LeadQualificationOutput(BaseModel):
    """
    Structured output returned by the lead-qualification crew for a single lead.

    Fields:
        customer_name     (str)  : Full name of the lead or customer.
        lead_score        (int)  : Overall lead quality score from 0 to 100.
                                   Values >= 70 are treated as high-priority.
        fit_score         (int)  : Qualitative product-fit score from 0 to 10.
        recommended_path  (str)  : The product or service the agent recommends
                                   for this lead (e.g. "Home Loan", "Debt Consolidation").
        risk_notes        (str)  : Free-text notes about risks or caveats the
                                   sales team should be aware of before engaging.
    """
    customer_name: str = Field(..., description="Lead/customer name.")
    lead_score: int = Field(..., ge=0, le=100, description="Validated lead score between 0 and 100.")
    fit_score: int = Field(..., ge=0, le=10, description="Qualitative fit score between 0 and 10.")
    recommended_path: str = Field(..., description="Recommended service or product path.")
    risk_notes: str = Field(..., description="Risk or caveat notes relevant to this lead.")


class EmailEngagementOutput(BaseModel):
    """
    Structured output returned by the email-engagement crew for a single lead.

    Fields:
        subject_line  (str) : A concise, personalised email subject line
                              crafted to maximise open rate.
        email_body    (str) : The full optimised email body, including
                              personalised greeting, value proposition, and
                              closing. Ready to send without further editing.
        primary_cta   (str) : The main call-to-action phrase or link text
                              (e.g. "Book a free consultation", "Apply now").
    """
    subject_line: str = Field(..., description="Suggested email subject line.")
    email_body: str = Field(..., description="Final optimized email body.")
    primary_cta: str = Field(..., description="Primary customer call to action.")


class RiskComplianceOutput(BaseModel):
    """
    Structured output returned by the risk-and-compliance crew for a customer
    or transaction review.

    Fields:
        risk_level           (str)        : Overall risk classification label
                                            (e.g. "Low", "Medium", "High", "Critical").
        top_risks            (List[str])  : Ordered list of the most significant
                                            risk items identified during the review.
        controls             (List[str])  : Recommended controls or mitigations
                                            that should be applied to address the
                                            identified risks.
        escalation_required  (bool)      : True if the case must be escalated to
                                            a compliance officer or senior reviewer;
                                            False if it can be handled at team level.
    """
    risk_level: str = Field(..., description="Final risk level classification.")
    top_risks: List[str] = Field(..., description="Top identified risk items.")
    controls: List[str] = Field(..., description="Recommended controls and mitigations.")
    escalation_required: bool = Field(..., description="Whether escalation is required.")


class SocialMediaPost(BaseModel):
    """
    A single social-media post produced by the content-pipeline crew.

    Used as an element inside ``ContentOutput.social_media_posts``.

    Fields:
        platform  (str) : Target platform for the post
                          (e.g. "LinkedIn", "X", "Instagram").
        content   (str) : Ready-to-publish post text including the core
                          message and a call-to-action. Should respect
                          the character limits of the target platform.
    """
    platform: str = Field(..., description="Social media platform, such as LinkedIn or X.")
    content: str = Field(..., description="Post content with concise message and CTA.")


class ContentOutput(BaseModel):
    """
    Aggregated structured output returned by the content-pipeline crew for a
    single content-generation run.

    Fields:
        blog_post           (str)               : A long-form blog article
                                                  formatted in Markdown. Covers
                                                  the topic in depth and is
                                                  suitable for publishing on the
                                                  bank's website or blog.
        social_media_posts  (List[SocialMediaPost]) : One or more platform-specific
                                                  posts derived from the same topic
                                                  as the blog post. Each entry
                                                  specifies its target platform and
                                                  ready-to-publish content.
    """
    blog_post: str = Field(..., description="Long-form blog post in markdown.")
    social_media_posts: List[SocialMediaPost] = Field(
        ..., description="List of social media posts derived from the same topic."
    )
