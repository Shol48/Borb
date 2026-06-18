"""Borb FastAPI backend entrypoint.

Wires together the API layer, the LLM provider layer, the agent core, the system
execution layer, the policy/authority layer and the audit layer.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.agent.core import AgentCore, SessionStore
from app.audit.logger import get_audit_logger
from app.config import get_settings
from app.llm.router import get_llm_provider
from app.schemas import ChatRequest, ChatResponse
from app.system.executor import SystemExecutor
from app.system.policy import PolicyEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("borb")


def build_agent() -> AgentCore:
    settings = get_settings()
    return AgentCore(
        settings=settings,
        llm=get_llm_provider(),
        executor=SystemExecutor(settings),
        policy=PolicyEngine(settings),
        audit=get_audit_logger(),
        sessions=SessionStore(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info(
        "Borb %s starting | env=%s authority_mode=%s provider=%s model=%s",
        __version__,
        settings.env,
        settings.authority_mode.value,
        settings.llm_provider.value,
        settings.llm_model,
    )
    if settings.is_authority:
        log.warning(
            "AUTHORITY mode is active: actions run WITHOUT policy checks or "
            "confirmation. Use only for local development/testing."
        )
    app.state.agent = build_agent()
    yield
    provider = getattr(app.state, "agent", None)
    if provider is not None:
        await provider.llm.aclose()


app = FastAPI(title="Borb", version=__version__, lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.env,
        "authority_mode": settings.authority_mode.value,
        "llm_provider": settings.llm_provider.value,
        "llm_model": settings.llm_model,
    }


@app.get("/config")
async def config() -> dict:
    """Non-secret view of the active backend configuration."""

    s = get_settings()
    return {
        "env": s.env,
        "authority_mode": s.authority_mode.value,
        "workspace_root": s.workspace_root,
        "capabilities": {
            "shell": s.allow_shell,
            "filesystem": s.allow_filesystem,
            "network": s.allow_network,
            "process_control": s.allow_process_control,
            "package_install": s.allow_package_install,
            "sudo": s.allow_sudo,
        },
        "llm_provider": s.llm_provider.value,
        "llm_model": s.llm_model,
        "agent_max_steps": s.agent_max_steps,
        "audit_log": s.audit_log,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    agent: AgentCore = app.state.agent
    return await agent.handle(request)


def run() -> None:
    """Console entrypoint: ``borb`` (see pyproject scripts)."""

    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.env == "development",
    )


if __name__ == "__main__":
    run()
