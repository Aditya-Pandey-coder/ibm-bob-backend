from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def payload():
    return {"repo_path": "/tmp/rootcause-demo-repo", "failing_test": "tests/test_api.py", "error_log": "JSON serialization changed"}


def test_post_shape():
    response = client.post("/api/investigate", json=payload())
    assert response.status_code == 200
    assert set(response.json()) == {"investigation_id", "status"}
    assert response.json()["status"] == "started"


def test_status_shape():
    identifier = client.post("/api/investigate", json=payload()).json()["investigation_id"]
    response = client.get(f"/api/investigation/{identifier}/status")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"investigation_id", "phase", "bisection_progress", "hypotheses"}
    assert {item["id"] for item in data["hypotheses"]} == {"race_condition", "dependency_bump", "off_by_one", "api_contract_break"}


def test_validation_and_missing_ids():
    assert client.post("/api/investigate", json={}).status_code == 422
    assert client.get("/api/investigation/not-found/status").status_code == 404
    assert client.get("/api/investigation/not-found/report").status_code == 404


def test_cors():
    response = client.options("/api/investigate", headers={"Origin": "http://127.0.0.1:5500", "Access-Control-Request-Method": "POST"})
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5500"
