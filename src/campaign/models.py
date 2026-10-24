"""Data models and schemas for Dakota's Cross-Scrip Syndicate Correlation and Campaign Intelligence."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class CampaignStatus(str, Enum):
    ACTIVE = "active"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class CampaignTier(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    CANDIDATE = "CANDIDATE"


class RelationshipType(str, Enum):
    SHARED_PROMOTER = "shared_promoter"
    SHARED_TEMPLATE = "shared_template"
    SHARED_URL = "shared_url"
    TEMPORAL_BURST = "temporal_burst"
    MARKET_CORROBORATION = "market_corroboration"
    SURVEILLANCE_FLAG = "surveillance_flag"
    BROAD_MARKET_CONTEXT = "broad_market_context"
    CORPORATE_DISCLOSURE = "corporate_disclosure"


class CampaignEvent(BaseModel):
    event_id: str
    campaign_id: str
    event_type: str = Field(description="tip, alert, market_anomaly, disclosure, action")
    ticker: str
    source_label: str
    event_timestamp: str = Field(description="Original event/observation publication time")
    retrieved_at: str = Field(description="Timestamp when Dakota ingested or evaluated this record")
    data_freshness: str = Field(default="LIVE", description="LIVE, DELAYED, CACHED, STALE, UNAVAILABLE")
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignRecord(BaseModel):
    campaign_id: str
    name: str
    status: CampaignStatus = CampaignStatus.ACTIVE
    tier: CampaignTier = CampaignTier.CANDIDATE
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    securities: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)
    relationship_explanations: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    alert_ids: list[str] = Field(default_factory=list)
    shared_urls: list[str] = Field(default_factory=list)
    shared_fingerprints: list[str] = Field(default_factory=list)
    time_window_hours: int = 24
    first_seen: str | None = None
    last_seen: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""
    acknowledged_at: str | None = None
    resolved_at: str | None = None
    dismissed_at: str | None = None
    jev_assessment: dict[str, Any] | None = None
    contradictions: list[str] = Field(default_factory=list)
    events: list[CampaignEvent] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["status"] = self.status.value
        d["tier"] = self.tier.value
        return d


class CampaignSummary(BaseModel):
    total_campaigns: int = 0
    active_count: int = 0
    monitoring_count: int = 0
    resolved_count: int = 0
    dismissed_count: int = 0
    high_tier_count: int = 0
    moderate_tier_count: int = 0
    candidate_tier_count: int = 0
    total_securities_involved: int = 0
    total_actors_tracked: int = 0
    last_updated: str | None = None


class NodeType(str, Enum):
    CAMPAIGN = "campaign"
    SECURITY = "security"
    ACTOR = "actor"
    MESSAGE = "message"
    ALERT = "alert"
    URL = "url"
    DISCLOSURE = "disclosure"


class EdgeType(str, Enum):
    PROMOTED_BY = "promoted_by"
    SHARED_TEMPLATE = "shared_template"
    SHARED_URL = "shared_url"
    TEMPORAL_BURST = "temporal_burst"
    MARKET_CORROBORATION = "market_corroboration"
    ASSOCIATED_DISCLOSURE = "associated_disclosure"
    CONTRADICTED_BY = "contradicted_by"
    MEMBER_SECURITY = "member_security"


class GraphNode(BaseModel):
    id: str
    type: NodeType
    label: str
    sublabel: str | None = None
    status: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: EdgeType
    label: str
    rationale: str
    confidence: float = 1.0
    evidence_references: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class CampaignGraph(BaseModel):
    campaign_id: str
    name: str
    tier: CampaignTier
    status: CampaignStatus
    confidence_score: float
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    contradictions: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Dakota graph models reflect observed correlations and analytical evidence tokens. "
        "They do not imply legal culpability or coordinated criminal intent."
    )

