"""PiAgent with a fake `pi` and a local git repo: no network, no API key. Run: python -m pytest"""

import json

import pytest
import os
import subprocess

import pipeline

os.environ.setdefault("ANTHROPIC_API_KEY", "test")

# A fake pi: makes its --session-dir ($6), then prints one JSON-mode answer event.
FAKE_PI = """#!/bin/sh
mkdir -p "$6"
{extra}
printf '{{"type":"message_end","message":{{"role":"assistant","content":[{{"type":"text","text":"%s"}}]}}}}\\n' "{answer}"
"""


def test_runs_pi_in_a_clone(tmp_path, monkeypatch):
    fake = tmp_path / "pi"
    fake.write_text(FAKE_PI.format(extra="", answer='cwd=$(basename "$PWD") prompt=$2 $(echo "$@" | grep -o -- --continue)'))
    fake.chmod(0o755)
    monkeypatch.setattr(pipeline, "PI_BIN", fake)
    monkeypatch.setattr(pipeline, "ensure_pi", lambda: None)

    src = tmp_path / "src"
    src.mkdir()
    subprocess.run("git init -q && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init", shell=True, cwd=src, check=True)

    out = pipeline.PiAgent().run(json.dumps({"prompt": "fix the bug", "repo": str(src)}))
    assert out["messages"][0].text == "cwd=repo prompt=fix the bug"

    plain = pipeline.PiAgent().run("hello")
    assert plain["messages"][0].text.endswith("prompt=hello")


def test_gitlab_token(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "t0k")
    assert pipeline.with_token("https://gitlab.com/g/p.git") == "https://oauth2:t0k@gitlab.com/g/p.git"
    assert pipeline.with_token("https://github.com/g/p.git") == "https://github.com/g/p.git"


def test_follow_up_on_a_session_continues_in_the_same_clone(tmp_path, monkeypatch):
    fake = tmp_path / "pi"
    fake.write_text(FAKE_PI.format(extra="touch made-by-pi", answer='prompt=$2 $(echo "$@" | grep -o -- --continue)'))
    fake.chmod(0o755)
    monkeypatch.setattr(pipeline, "PI_BIN", fake)
    monkeypatch.setattr(pipeline, "ensure_pi", lambda: None)
    monkeypatch.setenv("HAYSTACK_SESSION_WORKSPACE", str(tmp_path / "session"))
    (tmp_path / "session").mkdir()
    src = tmp_path / "src"
    src.mkdir()
    subprocess.run("git init -q && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init", shell=True, cwd=src, check=True)

    first = pipeline.PiAgent().run(json.dumps({"prompt": "build it", "repo": str(src)}))
    assert first["messages"][0].text == "prompt=build it"
    second = pipeline.PiAgent().run(json.dumps({"prompt": "adjust it", "repo": str(src)}))
    assert second["messages"][0].text == "prompt=adjust it --continue"
    assert (tmp_path / "session" / "repo" / "made-by-pi").exists()  # same clone, not re-cloned


def test_tool_calls_become_agent_spans(tmp_path, monkeypatch):
    events = [
        {"type": "turn_start"},
        {"type": "message_start", "message": {"role": "assistant"}},
        {"type": "message_end", "message": {"role": "assistant", "content": [{"type": "toolCall", "name": "bash"}]}},
        {"type": "tool_execution_start", "toolCallId": "t1", "toolName": "bash", "args": {"command": "ls"}},
        {"type": "tool_execution_end", "toolCallId": "t1", "toolName": "bash", "result": "a.txt", "isError": False},
        {"type": "turn_end"},
        {"type": "turn_start"},
        {"type": "message_start", "message": {"role": "assistant"}},
        {"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}},
        {"type": "turn_end"},
    ]
    fake = tmp_path / "pi"
    fake.write_text("#!/bin/sh\ncat <<'EOF'\n" + "\n".join(json.dumps(e) for e in events) + "\nEOF\n")
    fake.chmod(0o755)
    spans = []

    class Recorder:
        def trace(self, name, tags=None, parent_span=None):
            span = type("Span", (), {"set_tag": lambda self, k, v: self.tags.__setitem__(k, v)})()
            span.name, span.tags = name, dict(tags or {})
            spans.append(span)
            return __import__("contextlib").nullcontext(span)

    monkeypatch.setattr(pipeline.tracing, "tracer", Recorder())
    assert pipeline.run_pi([str(fake)], "list files", tmp_path, None) == "done"
    tool = next(s for s in spans if s.name == "haystack.agent.step.tool")
    assert tool.tags["haystack.tool.name"] == "bash"
    assert tool.tags["haystack.agent.step.tool.input"] == {"command": "ls"}
    assert tool.tags["haystack.agent.step.tool.output"] == "a.txt"
    assert [s.name for s in spans].count("haystack.agent.step") == 2
    assert spans[0].tags["haystack.agent.output"] == "done"


def test_refuses_to_run_without_the_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        pipeline.PiAgent().run("hello")
