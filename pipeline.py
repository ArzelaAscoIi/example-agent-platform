"""One pi coding agent (https://pi.dev) as a Haystack pipeline.

Query: plain text (the prompt), or JSON {"prompt": "...", "repo": "https://gitlab.com/group/project.git"}.
The agent runs in a fresh directory with shell and outbound network; with "repo" it starts in a clone.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from haystack import Pipeline, component
from haystack.dataclasses import ChatMessage

NODE_VERSION = "v22.12.0"
PI_VERSION = "0.73.1"
HOME = Path.home()
NODE_DIR = HOME / f"node-{NODE_VERSION}-linux-x64"
PI_BIN = HOME / ".pi-cli" / "bin" / "pi"


def sh(cmd: list[str] | str, cwd: Path | None = None, timeout: int = 300, env: dict | None = None) -> str:
    # stdin=DEVNULL: the platform worker reads its control frames (heartbeats) from stdin; a child that
    # inherits it eats them and the worker is killed as hung after 60s.
    out = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    if out.returncode:
        raise RuntimeError(f"{cmd!r} failed ({out.returncode}):\n{out.stdout[-2000:]}{out.stderr[-2000:]}")
    return out.stdout


def ensure_pi() -> dict:
    """Node and pi, installed once per pod (the runtime image has neither). Returns the env pi runs with."""
    env = {**os.environ, "PATH": f"{NODE_DIR / 'bin'}:{PI_BIN.parent}:{os.environ.get('PATH', '')}"}
    if not (NODE_DIR / "bin" / "node").exists():
        sh(f"curl -sSL https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-linux-x64.tar.xz | tar -xJ -C {HOME}")
    if not PI_BIN.exists():
        sh(["npm", "install", "-g", "--prefix", str(PI_BIN.parent.parent), f"@mariozechner/pi-coding-agent@{PI_VERSION}"], env=env)
    return env


def parse(query: str) -> tuple[str, str | None]:
    if query.lstrip().startswith("{"):
        body = json.loads(query)
        return body["prompt"], body.get("repo")
    return query, None


def with_token(repo: str) -> str:
    """GitLab over HTTPS with GITLAB_TOKEN when it is set; any other URL is used as is."""
    token = os.environ.get("GITLAB_TOKEN")
    if token and repo.startswith("https://gitlab.com/"):
        return repo.replace("https://", f"https://oauth2:{token}@", 1)
    return repo


@component
class PiAgent:
    @component.output_types(messages=list[ChatMessage])
    def run(self, query: str) -> dict:
        prompt, repo = parse(query)
        env = ensure_pi()
        # ponytail: fresh temp dir per run, lost when the pod restarts. Keep state that must survive behind an API.
        work = Path(tempfile.mkdtemp(prefix="pi-"))
        if repo:
            sh(["git", "clone", "--depth", "1", with_token(repo), str(work / "repo")], env=env)
            work = work / "repo"
        answer = sh([str(PI_BIN), "-p", prompt, "--no-session"], cwd=work, env=env, timeout=3600)
        return {"messages": [ChatMessage.from_assistant(answer.strip())]}


pipeline = Pipeline()
pipeline.add_component("pi", PiAgent())
