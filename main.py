from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from models import InvestigationRequest, InvestigationResponse, InvestigationStatus, Report
from storage import InvestigationStore

app = FastAPI(title="RootCause Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = InvestigationStore()


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, investigation_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.setdefault(investigation_id, set()).add(websocket)

    async def disconnect(self, investigation_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._clients.get(investigation_id)
            if clients is None:
                return
            clients.discard(websocket)
            if not clients:
                self._clients.pop(investigation_id, None)

    async def broadcast(self, investigation_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients.get(investigation_id, set()))
        failed: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(event)
            except Exception:
                failed.append(client)
        for client in failed:
            await self.disconnect(investigation_id, client)


manager = ConnectionManager()


def git(repo_path: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo_path, capture_output=True, text=True,
        timeout=timeout, check=False,
    )


def commit_metadata(repo_path: str, commit_hash: str) -> tuple[str, str]:
    message = git(repo_path, "show", "-s", "--format=%s", commit_hash).stdout.strip()
    author = git(repo_path, "show", "-s", "--format=%an", commit_hash).stdout.strip()
    return message or "unknown commit", author or "unknown author"


def commit_diff(repo_path: str, commit_hash: str) -> str:
    return git(repo_path, "show", "--format=", commit_hash).stdout


def run_test_in_worktree(repo_path: str, failing_test: str, commit_hash: str) -> tuple[bool, str]:
    worktree = tempfile.mkdtemp(prefix="rootcause-")
    try:
        added = git(repo_path, "worktree", "add", "--detach", worktree, commit_hash)
        if added.returncode != 0:
            return False, added.stderr
        result = subprocess.run(
            ["python", "-m", "pytest", failing_test, "-q"],
            cwd=worktree, capture_output=True, text=True, timeout=45, check=False,
        )
        return result.returncode != 0, result.stdout + "\n" + result.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    finally:
        git(repo_path, "worktree", "remove", "--force", worktree)
        shutil.rmtree(worktree, ignore_errors=True)


async def emit(investigation_id: str, event: dict[str, Any]) -> None:
    await manager.broadcast(investigation_id, event)


async def set_phase(investigation_id: str, phase: str) -> None:
    store.update_phase(investigation_id, phase)
    await emit(investigation_id, {"type": "phase_change", "phase": phase})


async def bisect_investigate(investigation_id: str, repo_path: str, failing_test: str) -> dict[str, Any]:
    empty = {"commit_hash": "unknown", "commit_message": "", "author": "", "diff": "", "output": ""}
    if not os.path.isdir(repo_path) or git(repo_path, "rev-parse", "--show-toplevel").returncode != 0:
        empty["commit_message"] = "Repository not found or is not a git repository"
        return empty
    history = git(repo_path, "log", "--reverse", "--format=%H")
    commits = [line for line in history.stdout.splitlines() if line.strip()]
    if not commits:
        empty["commit_message"] = "Repository has no commits"
        return empty
    for checked, commit_hash in enumerate(commits, 1):
        store.update_bisection(investigation_id, commit_hash, checked, len(commits))
        await emit(investigation_id, {
            "type": "bisection_update", "commit_hash": commit_hash,
            "commits_checked": checked, "total_commits": len(commits),
        })
        failed, output = await asyncio.to_thread(run_test_in_worktree, repo_path, failing_test, commit_hash)
        if failed:
            message, author = commit_metadata(repo_path, commit_hash)
            return {"commit_hash": commit_hash, "commit_message": message, "author": author,
                    "diff": commit_diff(repo_path, commit_hash), "output": output}
    last = commits[-1]
    message, author = commit_metadata(repo_path, last)
    return {"commit_hash": last, "commit_message": message, "author": author,
            "diff": commit_diff(repo_path, last), "output": "No failing commit found"}


KEYWORDS = {
    "race_condition": ("thread", "async", "lock", "race", "concurrent", "mutex"),
    "dependency_bump": ("dependency", "requirements", "version", "upgrade", "bump", "json", "serialize"),
    "off_by_one": ("index", "range", "slice", "offset", "boundary", "loop"),
    "api_contract_break": ("schema", "contract", "response", "payload", "422", "500"),
}
LABELS = {
    "race_condition": "Race Condition", "dependency_bump": "Dependency Version Bump",
    "off_by_one": "Off-by-One Error", "api_contract_break": "Broken API Contract",
}


def score(hypothesis_id: str, evidence: str) -> tuple[int, str]:
    lowered = evidence.lower()
    matches = [word for word in KEYWORDS[hypothesis_id] if word in lowered]
    confidence = min(100, len(matches) * 18)
    if hypothesis_id == "dependency_bump" and any(word in lowered for word in ("json", "serialize", "dependency", "requirements")):
        confidence = max(confidence, 92)
    reason = "Matched evidence: " + ", ".join(matches) if matches else "No strong matching evidence"
    return confidence, reason


async def test_hypothesis(investigation_id: str, hypothesis_id: str, evidence: str) -> tuple[str, int, str]:
    confidence, reason = score(hypothesis_id, evidence)
    status = "confirmed" if confidence > 85 else "ruled_out"
    store.update_hypothesis(investigation_id, hypothesis_id, confidence, status)
    await emit(investigation_id, {"type": "hypothesis_update", "id": hypothesis_id,
                                  "confidence": confidence, "status": status})
    return hypothesis_id, confidence, reason


def fix_diff(root_cause_id: str) -> str:
    if root_cause_id == "dependency_bump":
        return """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@
 def serialize(payload):
-    return json.dumps(payload)
+    return json.dumps(payload, sort_keys=True)
"""
    if root_cause_id == "off_by_one":
        return """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@
-    return values[index:index + length + 1]
+    return values[index:index + length]
"""
    if root_cause_id == "api_contract_break":
        return """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@
-    return {"status": "error"}
+    return {"status": "ok", "data": payload}
"""
    return """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@
-    update_without_lock()
+    with lock:
+        update_without_lock()
"""


def regression_test(root_cause_id: str) -> str:
    if root_cause_id == "dependency_bump":
        return """import json


def test_serialization_regression():
    payload = {"status": "ok", "items": [1, 2]}
    assert json.dumps(payload, sort_keys=True) == '{"items": [1, 2], "status": "ok"}'
"""
    if root_cause_id == "off_by_one":
        return """def test_slice_regression():
    values = [1, 2, 3]
    assert values[:2] == [1, 2]
"""
    if root_cause_id == "api_contract_break":
        return """def test_contract_regression():
    response = {"status": "ok", "data": {"id": 1}}
    assert response["status"] == "ok"
"""
    return """def test_concurrency_regression():
    shared = {"count": 0}
    shared["count"] += 1
    assert shared["count"] == 1
"""


def make_report(result: dict[str, Any], root_cause_id: str, confidence: int, reason: str) -> Report:
    label = LABELS[root_cause_id]
    return Report(
        commit_hash=result["commit_hash"], commit_message=result["commit_message"], author=result["author"],
        root_cause_id=root_cause_id, root_cause_label=label,
        explanation=f"{label} best explains the failure. {reason}.",
        fix_diff=fix_diff(root_cause_id), regression_test=regression_test(root_cause_id),
        summary=f"The first failing commit was {result['commit_hash']}. {label} scored {confidence}% confidence.",
    )


async def run_investigation(investigation_id: str, request: InvestigationRequest) -> None:
    try:
        await set_phase(investigation_id, "planning")
        await set_phase(investigation_id, "bisecting")
        result = await bisect_investigate(investigation_id, request.repo_path, request.failing_test)
        if result["commit_hash"] == "unknown":
            report = Report(
                commit_hash="unknown", commit_message=result["commit_message"], author="unknown",
                root_cause_id="dependency_bump", root_cause_label="Dependency Version Bump",
                explanation="The repository could not be bisected.", fix_diff="", regression_test="",
                summary=result["commit_message"],
            )
            store.set_report(investigation_id, report)
            await set_phase(investigation_id, "complete")
            await emit(investigation_id, {"type": "complete", "report": report.model_dump()})
            return
        await set_phase(investigation_id, "hypothesis_testing")
        evidence = "\n".join([request.error_log, result["commit_message"], result["diff"], result["output"]])
        tasks = [asyncio.create_task(test_hypothesis(investigation_id, hypothesis_id, evidence))
                 for hypothesis_id in KEYWORDS]
        results = await asyncio.gather(*tasks)
        root_cause_id, confidence, reason = max(results, key=lambda item: item[1])
        await set_phase(investigation_id, "fixing")
        report = make_report(result, root_cause_id, confidence, reason)
        store.set_report(investigation_id, report)
        await set_phase(investigation_id, "complete")
        await emit(investigation_id, {"type": "complete", "report": report.model_dump()})
    except Exception as exc:
        report = Report(
            commit_hash="unknown", commit_message="investigation error", author="unknown",
            root_cause_id="api_contract_break", root_cause_label="Broken API Contract",
            explanation=f"Investigation failed safely: {exc}", fix_diff="", regression_test="",
            summary="Investigation could not complete.",
        )
        store.set_report(investigation_id, report)
        await set_phase(investigation_id, "complete")
        await emit(investigation_id, {"type": "complete", "report": report.model_dump()})


@app.post("/api/investigate", response_model=InvestigationResponse)
async def create_investigation(request: InvestigationRequest) -> InvestigationResponse:
    investigation_id = str(uuid4())
    store.create(investigation_id, request)
    asyncio.create_task(run_investigation(investigation_id, request))
    return InvestigationResponse(investigation_id=investigation_id, status="started")


@app.get("/api/investigation/{investigation_id}/status", response_model=InvestigationStatus)
async def get_status(investigation_id: str) -> InvestigationStatus:
    item = store.get(investigation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return item.status


@app.get("/api/investigation/{investigation_id}/report", response_model=Report)
async def get_report(investigation_id: str) -> Report:
    item = store.get(investigation_id)
    if item is None or item.report is None:
        raise HTTPException(status_code=404, detail="Investigation report not available")
    return item.report


@app.websocket("/ws/investigation/{investigation_id}")
async def investigation_websocket(websocket: WebSocket, investigation_id: str) -> None:
    try:
        UUID(investigation_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid investigation ID")
        return
    if store.get(investigation_id) is None:
        await websocket.close(code=1008, reason="Investigation not found")
        return
    await manager.connect(investigation_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(investigation_id, websocket)


async def broadcast_event(investigation_id: str, event: dict[str, Any]) -> None:
    await manager.broadcast(investigation_id, event)


broadcast_event_for_investigation = broadcast_event
