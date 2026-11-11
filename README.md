# example-agent-platform

Run the [pi coding agent](https://pi.dev) as a service on the Haystack Enterprise Platform.

Each request starts pi in a fresh directory. The agent has a shell and outbound network, and can start in a clone of a GitLab (or any git) repository. Node and pi are installed on the pod on first use.

| File | What it is |
|---|---|
| `pipeline.py` | The pipeline: one `PiAgent` component that runs `pi -p <prompt>` |
| `pipeline.io.yaml` | Inputs, outputs and Python dependencies of the service |
| `test_pipeline.py` | Offline test with a fake `pi` |
| `examples/echo-gateway/pipeline.yaml` | Smallest possible service: returns the query as the answer, no model or secret needed |

## Run it

1. Install the CLI and log in:
   ```sh
   pip install haystack-enterprise-sdk
   haystack-enterprise login
   ```
2. Add workspace secrets (Settings → Secrets). The pipeline reads them as environment variables:
   - `ANTHROPIC_API_KEY`. For another provider, add its key (e.g. `OPENAI_API_KEY`) and set the secret `PI_PROVIDER` (e.g. `openai`)
   - `GITLAB_TOKEN` (optional, a token with `read_repository`, plus `write_repository` if agents push)
3. Try it in the sandbox, without deploying:
   ```sh
   haystack-enterprise run pipeline.py --workspace-name <workspace>
   ```
4. Deploy it as a service:
   ```sh
   haystack-enterprise deploy pipeline.py pi-agent --workspace-name <workspace>
   ```
5. Send a query, plain text or JSON:
   ```json
   {"prompt": "Run the tests and fix the first failure", "repo": "https://gitlab.com/group/project.git"}
   ```

## Smallest service first

To check your workspace and key work before adding pi, deploy the echo example and send it a query:

```sh
export API_KEY=$DEEPSET_API_KEY
haystack-enterprise deploy examples/echo-gateway/pipeline.yaml echo-gateway --workspace-name "$DEEPSET_WORKSPACE"
```

The deploy prints the model name `<workspace>/<service id>`. Query the service with its id; the answer is your query:

```sh
curl -X POST "https://api.cloud.deepset.ai/api/v1/workspaces/$DEEPSET_WORKSPACE/deployments/<service id>/search" \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"queries": ["hello"]}'
```

## Chat sessions (durable)

Submit each request as a durable run with a `session_id`. The run survives a pod restart, and its session workspace (the repo clone and pi's conversation) is saved after every run and restored on the next run with the same `session_id`, on any pod. A chat that lets users build and adjust a UI sends every message of one conversation with the same `session_id`:

```sh
python tools/durable_run.py ui-42 '{"prompt": "Create web/index.html with a hello page", "repo": "https://gitlab.com/group/project.git"}'
python tools/durable_run.py ui-42 "Make the heading blue"   # same clone, pi remembers the first request
```

The first request clones `repo`; follow-ups work in that clone (sending `repo` again is fine, it is not cloned twice). A new `session_id` starts clean. Under the hood: `POST .../deployments/<service id>/executions` with `{"query": ..., "session_id": ...}` and an `Idempotency-Key` header, then `GET .../executions/<execution_id>` until `status` is `completed`. See [Use durable runs](https://docs.cloud.deepset.ai/docs/use-durable-runs).
## Long runs

A plain request is cut off after 15 minutes. For longer agent runs, submit the query as a durable run: it survives a pod restart and starts again on a new pod. See [Use durable runs](https://docs.cloud.deepset.ai/docs/use-durable-runs). A service schedule (cron) can start runs on a timer.

## Limits

- Without a `session_id`, files on disk are lost when the run ends. Keep state other services need (results, agent-to-agent messages) behind an API.
- One request runs one agent. For Dev, Ops and Tester agents, deploy one service each, or put the role in the prompt.
- Pin a different pi or Node version in `pipeline.py` (`PI_VERSION`, `NODE_VERSION`).

## Work on it with an agent

`AGENTS.md` tells coding agents (pi, Claude Code, Cursor) how this repo works; `CLAUDE.md` points to it. Agents get platform access (traces, logs, deployments, docs) in two ways:

- MCP clients load `.mcp.json`, which connects to `https://api.cloud.deepset.ai/mcp` with `DEEPSET_API_KEY`.
- pi has no MCP, so it calls the same tools from the shell: `python tools/mcp_call.py` lists them, `python tools/mcp_call.py <tool> '<json args>'` calls one.

The `debug-service` skill (`.agents/skills/`, linked into `.claude/skills/`) walks an agent from a failed run to its cause. Copy `.env.example` to `.env` and fill it in first.

## Test

```sh
pip install haystack-ai==3.1.1 pytest
python -m pytest
```
