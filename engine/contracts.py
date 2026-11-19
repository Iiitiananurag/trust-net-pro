from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class PREvent(BaseModel):
    pr_id: str
    repo: str
    author: str
    title: str
    body: str = ""
    diff: str = ""
    opened_at: datetime
    author_created_at: datetime | None = None
    event_kind: Literal["pull_request", "issue"] = "pull_request"


class TrustEdge(BaseModel):
    src: str
    dst: str
    weight: float = Field(ge=0, le=1)


class Signal(BaseModel):
    project: str
    account: str
    kind: Literal["vouch", "denounce"]
    reason: str = ""
    at: datetime
    ttl_days: int | None = Field(default=90, ge=1)


class AppealRequest(BaseModel):
    project: str
    account: str
    reason: str = ""


class AnalysisReport(BaseModel):
    pr_id: str
    contributor: str
    viewer: str = "patricia"
    trust_score: float
    risk: Literal["low", "neutral", "elevated"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    campaign_id: str | None = None
    sybil_flagged: bool = False
    campaign_details: dict[str, Any] | None = None
