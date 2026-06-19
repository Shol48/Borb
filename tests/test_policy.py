from app.config import AuthorityMode, Settings
from app.schemas import PolicyDecisionType, ShellAction
from app.system.policy import PolicyEngine


def _settings(**overrides) -> Settings:
    base = dict(
        authority_mode=AuthorityMode.NORMAL,
        workspace_root="/workspace",
        allow_shell=True,
        allow_filesystem=True,
        allow_network=True,
        allow_sudo=False,
        allow_package_install=False,
    )
    base.update(overrides)
    return Settings(**base)


def test_authority_mode_allows_everything():
    engine = PolicyEngine(_settings(authority_mode=AuthorityMode.AUTHORITY))
    decision = engine.evaluate(ShellAction(command="rm -rf /"))
    assert decision.decision == PolicyDecisionType.ALLOW


def test_normal_mode_blocks_sudo_when_disabled():
    engine = PolicyEngine(_settings(allow_sudo=False))
    decision = engine.evaluate(ShellAction(command="sudo reboot"))
    assert decision.decision == PolicyDecisionType.BLOCK


def test_normal_mode_blocks_shell_when_disabled():
    engine = PolicyEngine(_settings(allow_shell=False))
    decision = engine.evaluate(ShellAction(command="ls"))
    assert decision.decision == PolicyDecisionType.BLOCK


def test_destructive_command_requires_confirm():
    engine = PolicyEngine(_settings())
    decision = engine.evaluate(ShellAction(command="rm important.txt"))
    assert decision.decision == PolicyDecisionType.CONFIRM


def test_shell_cwd_outside_workspace_requires_confirm():
    engine = PolicyEngine(_settings())
    decision = engine.evaluate(ShellAction(command="ls", cwd="/etc"))
    assert decision.decision == PolicyDecisionType.CONFIRM


def test_shell_inside_workspace_allowed():
    engine = PolicyEngine(_settings())
    decision = engine.evaluate(ShellAction(command="ls", cwd="/workspace/sub"))
    assert decision.decision == PolicyDecisionType.ALLOW
