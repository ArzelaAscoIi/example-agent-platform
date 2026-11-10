"""PiAgent with a fake `pi` and a local git repo: no network, no API key. Run: python -m pytest"""

import json
import subprocess

import pipeline


def test_runs_pi_in_a_clone(tmp_path, monkeypatch):
    fake = tmp_path / "pi"
    fake.write_text('#!/bin/sh\necho "cwd=$(basename "$PWD") prompt=$2"\n')
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
