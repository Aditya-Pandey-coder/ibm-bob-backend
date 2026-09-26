from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from models import BisectionProgress, Hypothesis, InvestigationRequest, InvestigationStatus, Report

HYPOTHESES = [
    ("race_condition", "Race Condition"),
    ("dependency_bump", "Dependency Version Bump"),
    ("off_by_one", "Off-by-One Error"),
    ("api_contract_break", "Broken API Contract"),
]


@dataclass
class Investigation:
    request: InvestigationRequest
    status: InvestigationStatus
    report: Report | None = None


class InvestigationStore:
    def __init__(self) -> None:
        self._items: dict[str, Investigation] = {}
        self._lock = RLock()

    def create(self, investigation_id: str, request: InvestigationRequest) -> Investigation:
        item = Investigation(
            request=request,
            status=InvestigationStatus(
                investigation_id=investigation_id,
                phase="planning",
                bisection_progress=BisectionProgress(),
                hypotheses=[
                    Hypothesis(id=hypothesis_id, label=label)
                    for hypothesis_id, label in HYPOTHESES
                ],
            ),
        )
        with self._lock:
            self._items[investigation_id] = item
        return item

    def get(self, investigation_id: str) -> Investigation | None:
        with self._lock:
            return self._items.get(investigation_id)

    def update_phase(self, investigation_id: str, phase: str) -> None:
        with self._lock:
            item = self._items.get(investigation_id)
            if item:
                item.status.phase = phase

    def update_bisection(self, investigation_id: str, commit_hash: str, checked: int, total: int) -> None:
        with self._lock:
            item = self._items.get(investigation_id)
            if item:
                item.status.bisection_progress.current_commit = commit_hash
                item.status.bisection_progress.commits_checked = checked
                item.status.bisection_progress.total_commits = total

    def update_hypothesis(self, investigation_id: str, hypothesis_id: str, confidence: int, status: str) -> None:
        with self._lock:
            item = self._items.get(investigation_id)
            if not item:
                return
            for hypothesis in item.status.hypotheses:
                if hypothesis.id == hypothesis_id:
                    hypothesis.confidence = confidence
                    hypothesis.status = status
                    return

    def set_report(self, investigation_id: str, report: Report) -> None:
        with self._lock:
            item = self._items.get(investigation_id)
            if item:
                item.report = report
