# Agent instructions

This repo runs the pi coding agent (https://pi.dev) as a service on the Haystack Enterprise Platform. Read `README.md` for what the service does.

## Files

- `pipeline.py`: the whole service. One `PiAgent` component: installs Node and pi on the pod, clones the repo from the query, runs `pi -p --mode json` and turns its events into trace spans (one step per pi turn, the model reply and each tool call).
- `pipeline.io.yaml`: service inputs, outputs and Python dependencies. Same basename as the pipeline, picked up by the CLI.
- `test_pipeline.py`: offline tests with a fake `pi`.
- `tools/mcp_call.py`: calls the platform MCP server from a shell.
- `.mcp.json`: the same MCP server for MCP clients (Claude Code, Cursor).

## Setup

`DEEPSET_API_KEY` and `DEEPSET_WORKSPACE` must be set (see `.env.example`). Load them with `set -a && . ./.env && set +a`.

## The loop

1. Change `pipeline.py`.
2. Test offline: `python -m pytest`. Must pass before anything else.
3. Run in the platform sandbox, no deploy: `haystack-enterprise run pipeline.py --workspace-name "$DEEPSET_WORKSPACE"`.
4. Deploy: `haystack-enterprise deploy pipeline.py pi-agent --workspace-name "$DEEPSET_WORKSPACE"`.
5. Send a query and read its trace and logs. Never call a change done before the trace of a real run shows it working. The `debug-service` skill has the steps.

## Platform access

- MCP clients: the `deepset` server from `.mcp.json`.
- Shell only (pi): `python tools/mcp_call.py` lists tools; `python tools/mcp_call.py <tool> '<json args>'` calls one.
- Docs: tool `search_docs` with `{"query": "..."}`.

Most tools need `"workspace"`. A service is a deployment: find its `deployment_id` with `list_deployments`.

## Rules

- Keep the service one file and the smallest code that works. No new dependency for what a few lines do.
- Never commit `.env` or a key. Secrets live as workspace secrets and reach the pod as environment variables.
- Files on the pod's disk are lost when a run restarts on a new pod. State that must survive goes through an API.
- Ask before tools that delete or cost money (`delete_*`, `rescore_experiment`, judged evaluators).
