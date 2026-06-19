# Borb

Borb is a **backend-centric, frontend-neutral AI assistant**. It accepts prompts
over an HTTP API, routes them to a local or external LLM, lets the model plan
**shell commands**, and executes them on the underlying system under the control
of a policy / authority layer.

The guiding principle: Borb is not a collection of narrow tools. It works
**exclusively through the shell** — every task (creating, reading or deleting
files, browsing, running tests, system tasks, …) is a shell command. Really
everything goes through the shell.

Borb has a **continuous memory** of the running conversation, and keeps a
**daily diary**: once a day it reflects on what happened and writes an entry to
disk, then clears its live context so it starts fresh. The diary is its
long-term memory, which it can re-read through the shell.

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
    core.py          #   orchestration loop (+ streaming) + global memory
    prompts.py       #   system prompt + action protocol
    system_prompt.md #   editable persona / protocol template
    planner.py       #   parse model reply -> structured plan
    diary.py         #   daily diary entry (reflect, persist, clear context)
    scheduler.py     #   wakes up daily at diary_time

  system/            # System Execution + Policy/Authority Layer
    executor.py      #   runs shell commands
    filesystem.py    #   file write + containment helpers
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

- `GET  /health`      — liveness + active mode/provider.
- `GET  /config`      — non-secret view of the active configuration.
- `POST /chat`        — main entry point (single JSON response).
- `POST /chat/stream` — same, streamed as Server-Sent Events.
- `POST /diary/run`   — manually trigger a diary entry now (testing).

`session_id` is optional: requests without one share Borb's single, continuous
conversation, so the frontend does not have to resend the chat history.

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

## Reply protocol

Borb first writes its reply in plain natural language (streamed to the user) and,
only when it needs to act, appends a single fenced ```json block with **shell
actions** at the end. The prose before the block is the user-facing answer /
narration ("what I'm about to do"); the backend parses, gates and executes the
actions:

````
Let me run the tests first.

```json
{
  "done": false,
  "actions": [
    {"type": "shell", "intent": "run_tests", "command": "pytest", "cwd": "/workspace/project"}
  ]
}
```
````

`shell` is the only action type — files, browsing and system tasks are all done
with ordinary commands (`cat`, `ls`, `echo`, `rm`, …).

In `normal` mode, commands that require confirmation are returned in
`pending_confirmations` instead of being executed, so any frontend (web or
voice) can decide how to confirm. In `authority` mode commands run directly.

### Streaming events

`POST /chat/stream` emits Server-Sent Events (`data: <json>\n\n`) with a `type`:
`start`, `thinking` (the model's separate reasoning channel, if any), `answer`
(reply text, streamed live), `tool_call` (a command is about to run),
`tool_result`, `paused` (confirmation needed), and `done`.

## Memory & diary

Borb keeps the whole running conversation in memory. To stop the context growing
forever, a scheduler wakes up daily at `BORB_DIARY_TIME` (default `21:00`): Borb
reflects on the day and the entry is saved as `YYYYMMDD_Borb_Diary_Entry.md` in
`BORB_DIARY_DIR` (default `~/Borb_Diary`). Afterwards the live context is cleared,
so the next day starts fresh. Borb re-reads past entries through the shell when it
needs to recall something.

## Tests

```bash
pytest
```

## Status

Implemented: FastAPI backend, `/chat` + `/chat/stream` endpoints, LLM provider
abstraction (Ollama + OpenAI-compatible) with streaming and a separate thinking
channel, shell-only action planning, system executor, `BORB_AUTHORITY_MODE`,
policy engine, audit logging, continuous in-memory conversation, and the daily
diary with context reset.

Not yet implemented (future): vLLM-specific provider niceties, persistent session
storage across restarts, process start/stop control, package-install workflows,
and the web/voice frontends.
