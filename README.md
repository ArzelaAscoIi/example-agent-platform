# example-agent-platform

Run the [pi coding agent](https://pi.dev) as a service on the Haystack Enterprise Platform.

Each request starts pi in a fresh directory. The agent has a shell and outbound network, and can start in a clone of a GitLab (or any git) repository. Node and pi are installed on the pod on first use.

| File | What it is |
|---|---|
| `pipeline.py` | The pipeline: one `PiAgent` component that runs `pi -p <prompt>` |
| `pipeline.io.yaml` | Inputs, outputs and Python dependencies of the service |
| `test_pipeline.py` | Offline test with a fake `pi` |

## Run it

1. Install the CLI and log in:
   ```sh
   pip install haystack-enterprise-sdk
   haystack-enterprise login
   ```
2. Add workspace secrets (Settings → Secrets). The pipeline reads them as environment variables:
   - `ANTHROPIC_API_KEY` (or any other provider key pi supports, e.g. `OPENAI_API_KEY`)
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

## Long runs

A plain request is cut off after 15 minutes. For longer agent runs, submit the query as a durable run: it survives a pod restart and starts again on a new pod. See [Use durable runs](https://docs.cloud.deepset.ai/docs/use-durable-runs). A service schedule (cron) can start runs on a timer.

## Limits

- Files on disk are lost when a run restarts on a new pod. Keep state that must survive (results, agent-to-agent messages) behind an API.
- One request runs one agent. For Dev, Ops and Tester agents, deploy one service each, or put the role in the prompt.
- Pin a different pi or Node version in `pipeline.py` (`PI_VERSION`, `NODE_VERSION`).

## Test

```sh
pip install haystack-ai==3.1.1 pytest
python -m pytest
```
