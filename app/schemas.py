"""Pydantic schemas shared across the API, agent and execution layers."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Action model
# --------------------------------------------------------------------------- #
class ActionType(str, Enum):
    SHELL = "shell"


class ShellAction(BaseModel):
    type: Literal[ActionType.SHELL] = ActionType.SHELL
    intent: Optional[str] = None
    command: str
    cwd: Optional[str] = None


# Borb works exclusively through the shell. Every task — creating, reading or
# deleting files, browsing, system tasks, etc. — is expressed as a shell command.
Action = ShellAction


# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #
class PolicyDecisionType(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    BLOCK = "block"


class PolicyDecision(BaseModel):
    decision: PolicyDecisionType
    reason: str = ""
    risk: str = "low"  # low | medium | high


# --------------------------------------------------------------------------- #
# Action result
# --------------------------------------------------------------------------- #
class ActionResult(BaseModel):
    type: ActionType
    intent: Optional[str] = None
    # echo of the relevant fields for transparency / audit
    command: Optional[str] = None
    path: Optional[str] = None
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    output: Optional[str] = None
    status: Literal["executed", "blocked", "confirm_required", "error"] = "executed"
    decision: Optional[PolicyDecision] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# API request / response
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    prompt: str
    frontend: str = "api"
    session_id: Optional[str] = None
    workspace: Optional[str] = None
    # allows a frontend to opt out of action execution for this single request
    execute_actions: bool = True


class PendingConfirmation(BaseModel):
    """Returned in normal mode when an action requires confirmation."""

    action: Dict[str, Any]
    decision: PolicyDecision


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    authority_mode: str
    actions: List[ActionResult] = Field(default_factory=list)
    pending_confirmations: List[PendingConfirmation] = Field(default_factory=list)
    steps: int = 0
