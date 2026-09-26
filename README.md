# RootCause Backend

FastAPI backend for the RootCause IBM Bob debugging workflow.

## Setup

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python demo_repo.py
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Smoke test

```bash
curl -X POST http://127.0.0.1:8000/api/investigate \
  -H 'Content-Type: application/json' \
  -d '{"repo_path":"/tmp/rootcause-demo-repo","failing_test":"tests/test_api.py","error_log":"JSON serialization changed after dependency bump"}'
```

Poll `/api/investigation/<id>/status` and `/api/investigation/<id>/report`. Connect to `ws://127.0.0.1:8000/ws/investigation/<id>` for live events.

## Validation

```bash
python -m py_compile main.py models.py storage.py demo_repo.py
pytest -q
```

The canonical API shapes are in `ROOTCAUSE_API_CONTRACT.md`. Storage is in-memory only, and CORS allows `http://127.0.0.1:5500`.
