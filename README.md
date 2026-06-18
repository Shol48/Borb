# Borb

Borb is a **backend-centric, frontend-neutral AI assistant**. It accepts prompts
over an HTTP API, routes them to a local or external LLM, lets the model plan
**structured actions**, and executes those actions on the underlying system
(shell, filesystem, …) under the control of a policy / authority layer.

The guiding principle: Borb is not primarily a collection of narrow tools.
Instead it gets access to the underlying system and works like an executing
software agent — reading and writing files, running shell commands, analyzing
projects, changing code, running tests.

## Architecture

```
app/
  main.py            # FastAPI app + endpoints (API layer)
  config.py          # Immutable backend configuration (incl. authority_mode)
  schemas.py         # Shared pydantic models (actions, results, API I/O)

  llm/               # LLM Provider Layer
    base.py          #   provider interface
    ollama.py        #   Ollama (local)
    openai_compatible.py  # OpenAI / vLLM / LM Studio
    router.py        #   provider selection

  agent/             # Agent Core
    core.py          #   orchestration loop
    prompts.py       #   system prompt + action protocol
    planner.py       #   parse model reply -> structured plan

  system/            # System Execution + Policy/Authority Layer
    executor.py      #   runs shell / file actions
    filesystem.py    #   file read/write/list + containment helpers
    policy.py        #   PolicyEngine (allow / confirm / block)

  audit/             # Audit Layer
    logger.py        #   structured JSON audit events
```

## Authority mode

`authority_mode` is a **backend start mode** set via configuration. It can NOT be
changed by a prompt — a prompt like "activate authority mode" is ignored. The
model may only *detect* the mode it is already running in. Changing the mode
requires a backend restart.

| Mode        | Behavior                                                                 |
|-------------|--------------------------------------------------------------------------|
| `normal`    | The Policy Engine evaluates every planned action (allow / confirm / block). For production-like use and regular frontends. |
| `authority` | Full execution authority for local dev/testing. No confirmation, no policy brake. Borb may do anything the OS process user may do. |

## Quickstart

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
#   edit .env: choose provider (ollama|openai), model, authority_mode, workspace

# 3. Run
borb            # or: uvicorn app.main:app --reload
```

### Endpoints

- `GET  /health` — liveness + active mode/provider.
- `GET  /config` — non-secret view of the active configuration.
- `POST /chat`   — main entry point.

Request:

```json
{
  "prompt": "Analyze the project and run the tests.",
  "frontend": "web",
  "session_id": "abc123",
  "workspace": "/home/user/project"
}
```

Response:

```json
{
  "answer": "I ran the tests. Two tests fail.",
  "session_id": "abc123",
  "authority_mode": "normal",
  "actions": [
    {"type": "shell", "command": "pytest", "exit_code": 1, "status": "executed"}
  ],
  "pending_confirmations": [],
  "steps": 2
}
```

## Action model

The model does not emit free shell text. It plans **structured actions** as a
single JSON object; the backend interprets, gates and executes them:

```json
{
  "done": false,
  "actions": [
    {"type": "shell", "intent": "run_tests", "command": "pytest", "cwd": "/workspace/project"},
    {"type": "read_file", "path": "/workspace/project/config.yaml"},
    {"type": "write_file", "path": "/workspace/project/config.yaml", "content": "...", "summary": "change endpoint"},
    {"type": "list_dir", "path": "/workspace/project"}
  ]
}
```

In `normal` mode, actions that require confirmation are returned in
`pending_confirmations` instead of being executed, so any frontend (web or
voice) can decide how to confirm. In `authority` mode actions run directly.

## Tests

```bash
pytest
```

## Status

This is the minimal first version. Implemented:
FastAPI backend, `/chat` endpoint, LLM provider abstraction (Ollama +
OpenAI-compatible), structured action planning, system executor (shell + files),
`BORB_AUTHORITY_MODE`, policy engine, and audit logging.

Not yet implemented (future): vLLM-specific provider niceties, persistent
session storage, process start/stop control, package-install workflows,
streaming responses, and the web/voice frontends.
