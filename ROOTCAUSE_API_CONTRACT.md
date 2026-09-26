# RootCause API Contract

## Endpoints

- `POST /api/investigate`
- `GET /api/investigation/{id}/status`
- `WS /ws/investigation/{id}`
- `GET /api/investigation/{id}/report`

### POST request

```json
{"repo_path":"string","failing_test":"string","error_log":"string"}
```

Response:

```json
{"investigation_id":"string (uuid)","status":"started"}
```

### Status response

```json
{
  "investigation_id":"string",
  "phase":"planning | bisecting | hypothesis_testing | fixing | complete",
  "bisection_progress":{"current_commit":"string","commits_checked":0,"total_commits":0},
  "hypotheses":[
    {"id":"race_condition","label":"Race Condition","confidence":0,"status":"testing"},
    {"id":"dependency_bump","label":"Dependency Version Bump","confidence":0,"status":"testing"},
    {"id":"off_by_one","label":"Off-by-One Error","confidence":0,"status":"testing"},
    {"id":"api_contract_break","label":"Broken API Contract","confidence":0,"status":"testing"}
  ]
}
```

Hypothesis status values are `testing`, `confirmed`, and `ruled_out`.

### WebSocket events

```json
{"type":"phase_change","phase":"..."}
{"type":"hypothesis_update","id":"...","confidence":0,"status":"..."}
{"type":"bisection_update","commit_hash":"...","commits_checked":0,"total_commits":0}
{"type":"complete","report":{}}
```

### Report response

```json
{
  "commit_hash":"string",
  "commit_message":"string",
  "author":"string",
  "root_cause_id":"race_condition | dependency_bump | off_by_one | api_contract_break",
  "root_cause_label":"string",
  "explanation":"string",
  "fix_diff":"string",
  "regression_test":"string",
  "summary":"string"
}
```

Backend: `http://127.0.0.1:8000`  
Frontend: `http://127.0.0.1:5500`
