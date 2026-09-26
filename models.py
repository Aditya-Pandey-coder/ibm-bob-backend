from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Phase = Literal["planning", "bisecting", "hypothesis_testing", "fixing", "complete"]
HypothesisStatus = Literal["testing", "confirmed", "ruled_out"]
RootCauseID = Literal["race_condition", "dependency_bump", "off_by_one", "api_contract_break"]


class InvestigationRequest(BaseModel):
    repo_path: str = Field(min_length=1)
    failing_test: str = Field(min_length=1)
    error_log: str = Field(min_length=1)


class InvestigationResponse(BaseModel):
    investigation_id: str
    status: Literal["started"]


class BisectionProgress(BaseModel):
    current_commit: str = ""
    commits_checked: int = Field(default=0, ge=0)
    total_commits: int = Field(default=0, ge=0)


class Hypothesis(BaseModel):
    id: RootCauseID
    label: str
    confidence: int = Field(default=0, ge=0, le=100)
    status: HypothesisStatus = "testing"


class InvestigationStatus(BaseModel):
    investigation_id: str
    phase: Phase
    bisection_progress: BisectionProgress
    hypotheses: list[Hypothesis]


class Report(BaseModel):
    commit_hash: str
    commit_message: str
    author: str
    root_cause_id: RootCauseID
    root_cause_label: str
    explanation: str
    fix_diff: str
    regression_test: str
    summary: str
