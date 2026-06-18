from app.agent.planner import parse_plan
from app.schemas import ShellAction, WriteFileAction


def test_plain_answer_without_json():
    plan = parse_plan("Hello, I am just answering.")
    assert plan.done is True
    assert plan.actions == []
    assert "answering" in plan.answer


def test_parses_actions_and_marks_not_done():
    text = """
    {"answer": "running tests", "done": false, "actions": [
        {"type": "shell", "intent": "run_tests", "command": "pytest"}
    ]}
    """
    plan = parse_plan(text)
    assert plan.done is False
    assert len(plan.actions) == 1
    assert isinstance(plan.actions[0], ShellAction)
    assert plan.actions[0].command == "pytest"


def test_extracts_json_from_markdown_fence():
    text = "Here you go:\n```json\n{\"answer\": \"done\", \"done\": true}\n```"
    plan = parse_plan(text)
    assert plan.answer == "done"
    assert plan.done is True


def test_skips_malformed_actions():
    text = """{"actions": [
        {"type": "write_file", "path": "/tmp/x", "content": "hi"},
        {"type": "totally_unknown"}
    ], "done": false}"""
    plan = parse_plan(text)
    assert len(plan.actions) == 1
    assert isinstance(plan.actions[0], WriteFileAction)
