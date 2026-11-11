"""One pi coding agent (https://pi.dev) as a Haystack pipeline.

Query: plain text (the prompt), or JSON {"prompt": "...", "repo": "https://gitlab.com/group/project.git"}.
The agent has a shell and outbound network; with "repo" it works in a clone. Submitted as a durable run with a
session_id, the clone and the conversation are kept for the next request on that session_id.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from haystack import Pipeline, component, tracing
from haystack.dataclasses import ChatMessage

NODE_VERSION = "v22.12.0"
PI_VERSION = "0.73.1"
# The provider whose key pi uses (a workspace secret, e.g. ANTHROPIC_API_KEY).
PI_PROVIDER = os.environ.get("PI_PROVIDER", "anthropic")
# Outside HOME: on session runs HOME is the session workspace, which is saved to S3 after every run.
TOOLS = Path(tempfile.gettempdir()) / "pi-tools"
NODE_DIR = TOOLS / f"node-{NODE_VERSION}-linux-x64"
PI_BIN = TOOLS / ".pi-cli" / "bin" / "pi"


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
        TOOLS.mkdir(parents=True, exist_ok=True)
        sh(f"curl -sSL https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-linux-x64.tar.xz | tar -xJ -C {TOOLS}")
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


def text_of(message: dict) -> str:
    return "".join(part.get("text", "") for part in message.get("content", []) if part.get("type") == "text")


def run_pi(cmd: list[str], prompt: str, cwd: Path, env: dict) -> str:
    """Runs pi in JSON mode and traces its run like a Haystack Agent: one step per pi turn, with the model reply
    (haystack.agent.step.llm) and each tool call (haystack.agent.step.tool) as spans. Returns pi's last answer."""
    spans: dict[str, tuple] = {}

    def start(key: str, name: str, tags: dict) -> None:
        cm = tracing.tracer.trace(name, tags=tags)
        spans[key] = (cm, cm.__enter__())

    def end(key: str, tags: dict | None = None) -> None:
        if key in spans:
            cm, span = spans.pop(key)
            for k, v in (tags or {}).items():
                span.set_tag(k, v)
            cm.__exit__(None, None, None)

    answer = ""
    start("run", "haystack.agent.run", {"haystack.component.name": "pi", "haystack.agent.input": prompt})
    with tempfile.TemporaryFile("w+") as err:  # stderr to a file: a full pipe would block pi
        proc = subprocess.Popen(cmd + ["--mode", "json"], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=err, text=True)
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind, message = event.get("type"), event.get("message") or {}
            if kind == "turn_start":
                start("turn", "haystack.agent.step", {})
            elif kind == "message_start" and message.get("role") == "assistant":
                start("llm", "haystack.agent.step.llm", {"haystack.component.name": "llm"})
            elif kind == "message_end" and message.get("role") == "assistant":
                end("llm", {"haystack.agent.step.llm.output": message})
                answer = text_of(message) or answer
            elif kind == "tool_execution_start":
                start(event["toolCallId"], "haystack.agent.step.tool",
                      {"haystack.tool.name": event["toolName"], "haystack.component.name": event["toolName"],
                       "haystack.agent.step.tool.input": event.get("args")})
            elif kind == "tool_execution_end":
                end(event["toolCallId"], {"haystack.agent.step.tool.output": event.get("result"),
                                          "haystack.tool.error": bool(event.get("isError"))})
            elif kind == "turn_end":
                end("turn")
        # ponytail: no own timeout; a plain request stops at 15 minutes and a durable run is cancellable.
        proc.wait()
        err.seek(0)
        stderr = err.read()
    for key in [k for k in spans if k != "run"]:
        end(key)
    end("run", {"haystack.agent.output": answer})
    if proc.returncode:
        raise RuntimeError(f"pi failed ({proc.returncode}):\n{stderr[-2000:]}")
    return answer


@component
class PiAgent:
    @component.output_types(messages=list[ChatMessage])
    def run(self, query: str) -> dict:
        prompt, repo = parse(query)
        key = f"{PI_PROVIDER.upper()}_API_KEY"
        if not os.environ.get(key):
            raise RuntimeError(f"Add {key} as a workspace secret: pi runs only with the {PI_PROVIDER} API key.")
        env = ensure_pi()
        # ponytail: fresh temp dir per run, lost when the pod restarts. Keep state that must survive behind an API.
        # A durable run with a session_id gets HAYSTACK_SESSION_WORKSPACE: restored before the run, saved after it.
        # The clone and pi's transcript live there, so a follow-up on the same session_id continues where this one stopped.
        work = Path(os.environ.get("HAYSTACK_SESSION_WORKSPACE") or tempfile.mkdtemp(prefix="pi-"))
        if repo and not (work / "repo").exists():
            sh(["git", "clone", with_token(repo), str(work / "repo")], env=env)
        cwd = work / "repo" if (work / "repo").exists() else work
        pi = [str(PI_BIN), "-p", prompt, "--provider", PI_PROVIDER, "--session-dir", str(work / ".pi-sessions")]
        if (work / ".pi-sessions").exists():
            pi.append("--continue")
        answer = run_pi(pi, prompt, cwd=cwd, env=env)
        return {"messages": [ChatMessage.from_assistant(answer.strip())]}


pipeline = Pipeline()
pipeline.add_component("pi", PiAgent())
