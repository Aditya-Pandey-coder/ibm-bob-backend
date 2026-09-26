from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True, text=True)


def create_demo_repo(repo_path: str) -> str:
    repo = Path(repo_path)
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "RootCause Demo"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "demo@example.com"], cwd=repo, check=True)

    (repo / "app.py").write_text("import json\n\ndef serialize(payload):\n    return json.dumps(payload)\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests/test_api.py").write_text("from app import serialize\n\ndef test_serialization():\n    assert serialize({'status': 'ok'}) == '{\"status\": \"ok\"}'\n", encoding="utf-8")
    commit(repo, "initial serializer app")

    (repo / "README.md").write_text("# Demo repository\n", encoding="utf-8")
    commit(repo, "document demo")

    (repo / "requirements.txt").write_text("json-serializer-lib==1.0.0\n", encoding="utf-8")
    commit(repo, "pin serializer dependency")

    (repo / "requirements.txt").write_text("json-serializer-lib==2.0.0\n", encoding="utf-8")
    (repo / "app.py").write_text("import json\n\ndef serialize(payload):\n    return json.dumps(payload, separators=(',', ':'))\n", encoding="utf-8")
    commit(repo, "bump dependency and change default serialization")

    (repo / "app.py").write_text("import json\n\ndef serialize(payload):\n    return json.dumps(payload, separators=(',', ':'))\n\ndef health():\n    return {'status': 'ok'}\n", encoding="utf-8")
    commit(repo, "add health helper")

    (repo / "README.md").write_text("# Demo repository\nThe dependency regression is intentional.\n", encoding="utf-8")
    commit(repo, "explain demo regression")
    return str(repo)


if __name__ == "__main__":
    print(create_demo_repo("/tmp/rootcause-demo-repo"))
