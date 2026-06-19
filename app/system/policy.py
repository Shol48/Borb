"""Policy / Authority layer.

Decides with which authority Borb may execute a planned action.

* In ``authority`` mode every action is allowed without any confirmation -
  there is no policy brake. Borb may do anything the OS process user may do.
* In ``normal`` mode this engine evaluates each action and returns one of
  ``allow`` / ``confirm`` / ``block`` depending on capability switches, the
  configured workspace root and a coarse risk heuristic.
"""

from __future__ import annotations

import re
from typing import List

from app.config import Settings
from app.schemas import (
    Action,
    PolicyDecision,
    PolicyDecisionType,
    ShellAction,
)
from app.system.filesystem import Filesystem

# Commands considered destructive / high risk in normal mode.
_DESTRUCTIVE_PATTERNS = [
    r"\brm\b",
    r"\bmkfs\b",
    r"\bdd\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bkill(all)?\b",
    r":\(\)\s*\{",  # fork bomb-ish
    r">\s*/dev/sd",
]

_NETWORK_PATTERNS = [r"\bcurl\b", r"\bwget\b", r"\bnc\b", r"\bssh\b", r"\bscp\b"]
_PACKAGE_PATTERNS = [
    r"\bapt(-get)?\s+install\b",
    r"\bpip\s+install\b",
    r"\bnpm\s+(install|i)\b",
    r"\byum\s+install\b",
    r"\bbrew\s+install\b",
]
_SUDO_PATTERN = r"\bsudo\b"


def _allow(reason: str = "", risk: str = "low") -> PolicyDecision:
    return PolicyDecision(decision=PolicyDecisionType.ALLOW, reason=reason, risk=risk)


def _confirm(reason: str, risk: str = "medium") -> PolicyDecision:
    return PolicyDecision(decision=PolicyDecisionType.CONFIRM, reason=reason, risk=risk)


def _block(reason: str, risk: str = "high") -> PolicyDecision:
    return PolicyDecision(decision=PolicyDecisionType.BLOCK, reason=reason, risk=risk)


class PolicyEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.fs = Filesystem()

    def evaluate(self, action: Action) -> PolicyDecision:
        # Authority mode: full execution authority, no brake.
        if self.settings.is_authority:
            return _allow("authority mode: unrestricted")

        if isinstance(action, ShellAction):
            return self._evaluate_shell(action)
        return _block(f"unknown action type: {getattr(action, 'type', '?')}")

    # --- shell -------------------------------------------------------------- #
    def _evaluate_shell(self, action: ShellAction) -> PolicyDecision:
        if not self.settings.allow_shell:
            return _block("shell execution is disabled (BORB_ALLOW_SHELL=false)")

        command = action.command or ""

        if _matches(command, _SUDO_PATTERN) and not self.settings.allow_sudo:
            return _block("sudo is disabled (BORB_ALLOW_SUDO=false)")

        if any_match(command, _PACKAGE_PATTERNS) and not self.settings.allow_package_install:
            return _block("package install is disabled (BORB_ALLOW_PACKAGE_INSTALL=false)")

        if any_match(command, _NETWORK_PATTERNS) and not self.settings.allow_network:
            return _block("network access is disabled (BORB_ALLOW_NETWORK=false)")

        if any_match(command, _DESTRUCTIVE_PATTERNS):
            return _confirm("command looks destructive", risk="high")

        # cwd containment check
        if action.cwd and not self._within_workspace(action.cwd):
            return _confirm(
                f"working directory is outside the workspace root "
                f"({self.settings.workspace_root})"
            )

        return _allow("shell command within policy")

    # --- helpers ------------------------------------------------------------ #
    def _within_workspace(self, path: str) -> bool:
        root = self.settings.workspace_root
        # An explicitly unrestricted root ("/") disables containment.
        if root in ("", "/"):
            return True
        return self.fs.is_within(path, root)


def _matches(text: str, pattern: str) -> bool:
    return re.search(pattern, text) is not None


def any_match(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)
