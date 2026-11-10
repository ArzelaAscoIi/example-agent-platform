---
name: debug-service
description: Find out what a deployed service did on the Haystack Enterprise Platform, from its traces, logs and stats. Use when a run failed, hung, returned something wrong, or after a deploy to prove a change works.
---

# Debug a service

Use the `deepset` MCP tools if you have them. Otherwise call the same tools from the shell:

```sh
python tools/mcp_call.py <tool> '<json args>'
```

Every call below needs `"workspace": "$DEEPSET_WORKSPACE"` (write the value, not the variable).

1. Find the service: `list_deployments` → note `deployment_id` of `pi-agent`. `get_deployment` shows the active revision and whether it is running.
2. List recent runs: `list_pipeline_traces` with `deployment_id` and `"limit": 10`. Each has a `query_id`; failed runs show their error.
3. Open one run: `get_pipeline_trace` with `deployment_id` and `query_id`. Find the span that failed or took long.
4. Read a span's inputs and outputs: `get_pipeline_trace_span_tags` with `query_id` and `span_id`. The `pi` span holds the prompt and pi's answer, or the command and its stderr when it failed.
5. Pod logs (install errors, crashes): `get_pipeline_logs` with `"pipeline_name": "pi-agent"`, optionally `"level": "error"`.
6. Load and limits: `get_deployment_stats` (volume, failures, durations) and `get_deployment_metrics` (CPU, memory per replica). A run killed at 15 minutes needs a durable run; memory at the limit needs a bigger size.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `curl ... nodejs.org` or `npm install` failed | No outbound network or registry down | Check logs; retry; pin another `NODE_VERSION` |
| `git clone` failed, 401/403 | `GITLAB_TOKEN` missing or lacks `read_repository` | Add or fix the workspace secret |
| pi exits with an auth error | No model key | Add `ANTHROPIC_API_KEY` (or the provider's key) as a workspace secret |
| Run stops at 15 minutes | Plain request time limit | Submit as a durable run (see README) |
| Files gone after a restart | Pod disk is not kept | Keep state behind an API |

Report back with the `query_id`, the failing span, the error text and the fix.
