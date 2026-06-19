"""Pydantic schemas shared across the API, agent and execution layers."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Action model
# --------------------------------------------------------------------------- #
class ActionType(str, Enum):
    SHELL = "shell"
    WEBSEARCH = "websearch"


class ShellAction(BaseModel):
    type: Literal[ActionType.SHELL] = ActionType.SHELL
    intent: Optional[str] = None
    command: str
    cwd: Optional[str] = None


class WebsearchAction(BaseModel):
    """Search the web for information.

    A first-class action (not routed through the shell) so the model never has
    to hand-craft search URLs or rely on a CLI tool being installed. The backend
    runs the query against the configured search provider and feeds the results
    back as an observation.
    """

    type: Literal[ActionType.WEBSEARCH] = ActionType.WEBSEARCH
    intent: Optional[str] = None
    query: str
    # Optional override of the configured default (BORB_WEBSEARCH_MAX_RESULTS).
    max_results: Optional[int] = None


# Borb works through the shell for system access (creating, reading or deleting
# files, browsing, system tasks, ...) and has a dedicated ``websearch`` action
# for looking things up on the internet. The union is discriminated on ``type``.
Action = Annotated[Union[ShellAction, WebsearchAction], Field(discriminator="type")]


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
    query: Optional[str] = None
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
