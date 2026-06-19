from app.agent.planner import parse_plan
from app.schemas import ShellAction


def test_plain_answer_without_json():
    plan = parse_plan("Hello, I am just answering.")
    assert plan.done is True
    assert plan.actions == []
    assert "answering" in plan.answer


def test_parses_actions_and_marks_not_done():
    text = """
    {"done": false, "actions": [
        {"type": "shell", "intent": "run_tests", "command": "pytest"}
    ]}
    """
    plan = parse_plan(text)
    assert plan.done is False
    assert len(plan.actions) == 1
    assert isinstance(plan.actions[0], ShellAction)
    assert plan.actions[0].command == "pytest"


def test_prose_then_fenced_json_block():
    text = (
        "Let me list the files first.\n\n"
        "```json\n"
        '{"actions": [{"type": "shell", "command": "ls -la"}], "done": false}\n'
        "```"
    )
    plan = parse_plan(text)
    # The prose before the block is the user-facing answer/narration.
    assert plan.answer == "Let me list the files first."
    assert plan.done is False
    assert len(plan.actions) == 1
    assert plan.actions[0].command == "ls -la"


def test_prose_only_is_a_final_answer():
    text = "Here you go: all done, nothing to run."
    plan = parse_plan(text)
    assert plan.actions == []
    assert plan.done is True
    assert plan.answer == text


def test_skips_malformed_actions():
    text = """{"actions": [
        {"type": "shell", "command": "ls"},
        {"type": "totally_unknown"}
    ], "done": false}"""
    plan = parse_plan(text)
    assert len(plan.actions) == 1
    assert isinstance(plan.actions[0], ShellAction)
    assert plan.actions[0].command == "ls"
