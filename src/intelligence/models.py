"""Unified Data Layer and Schemas for Dakota Intelligence Core."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    MARKET = "market"
    NEWS = "news"
    SOCIAL = "social"
    INVESTIGATION = "investigation"
    CAMPAIGN = "campaign"
    PORTFOLIO = "portfolio"
    REGULATORY = "regulatory"
    TECHNICAL = "technical"


class ObservationType(str, Enum):
    DIRECTLY_OBSERVED = "directly_observed"
    MODEL_INFERRED = "model_inferred"
    UNVERIFIED_CLAIM = "unverified_claim"


class EvidenceItem(BaseModel):
    id: str = Field(description="Unique evidence identifier, e.g. E1, E2")
    type: EvidenceType = Field(default=EvidenceType.NEWS)
    title: str = Field(description="Headline, indicator title, or record summary")
    snippet: str = Field(description="Directly quoted text or observation excerpt")
    full_content: str | None = Field(default=None, description="Full article or body if available")
    source_name: str = Field(description="Source provider: Yahoo Finance, NSE, Telegram, X/DDGS, etc.")
    source_url: str | None = Field(default=None, description="Direct URL to original record if available")
    entity_id: str | None = Field(default=None, description="Ticker, company name, or channel identifier")
    published_at: str | None = Field(default=None, description="Original publication/occurrence timestamp")
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Source reliability index")
    verified: bool = Field(default=True, description="Whether this source is verified or an unauthenticated claim")
    observation_type: ObservationType = Field(default=ObservationType.DIRECTLY_OBSERVED)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimFinding(BaseModel):
    id: str = Field(default_factory=lambda: f"claim_{datetime.now(timezone.utc).strftime('%H%M%S%f')[:10]}")
    claim: str = Field(description="Specific finding or statement")
    status: str = Field(default="directly_observed", description="directly_observed | model_inferred | unverified | contradicted")
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradictory_evidence_ids: list[str] = Field(default_factory=list)
    severity: str = Field(default="low", description="low | medium | high | critical")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    notes: str | None = None


class TimelineEvent(BaseModel):
    date: str
    title: str
    description: str
    evidence_id: str | None = None


class Citation(BaseModel):
    index: int
    evidence_id: str
    label: str = Field(description="E.g. [E1]")
    source_name: str
    source_url: str | None = None
    snippet: str
    observation_type: str = "directly_observed"


class IntelligenceQuery(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    active_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional client state: current ticker, investigation_id, page route",
    )
    filters: dict[str, Any] | None = None
    stream: bool = False


class IntelligenceAnswer(BaseModel):
    query: str
    conversation_id: str
    summary: str
    detailed_text: str
    findings: list[ClaimFinding] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    confidence_score: float = Field(default=0.85, ge=0.0, le=1.0)
    confidence_rationale: str = ""
    unknowns_and_limitations: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    next_investigative_steps: list[str] = Field(default_factory=list)
    provider_info: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IntelligenceReport(BaseModel):
    id: str
    title: str
    report_type: str
    executive_summary: str
    scope_and_methodology: str
    key_findings: list[ClaimFinding] = Field(default_factory=list)
    evidence_references: list[EvidenceItem] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    conflicting_information: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_list: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SearchFilter(BaseModel):
    search: str = ""
    entity: str = ""
    source_types: list[str] = Field(default_factory=list)
    risk_band: str = ""
    start_date: str | None = None
    end_date: str | None = None
    page: int = 1
    limit: int = 20


class SearchResultItem(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str = ""
    snippet: str = ""
    score: float | None = None
    band: str | None = None
    url: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackItem(BaseModel):
    answer_id: str
    query: str
    feedback_type: str = "general"
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
