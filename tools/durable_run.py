"""Submit a query as a durable run on a session and wait for pi's answer.

  python tools/durable_run.py <session_id> '<prompt or JSON {"prompt": ..., "repo": ...}>'

Same session_id = same clone and same conversation. Needs DEEPSET_API_KEY, DEEPSET_WORKSPACE and
DEEPSET_SERVICE_ID (the service's id, printed by `haystack-enterprise deploy`).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "https://api.cloud.deepset.ai/api/v1/workspaces/{}/deployments/{}/executions".format(
    os.environ["DEEPSET_WORKSPACE"], os.environ["DEEPSET_SERVICE_ID"]
)
HEADERS = {"Authorization": f"Bearer {os.environ['DEEPSET_API_KEY']}", "Content-Type": "application/json"}


def call(url: str, body: dict | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode() if body else None, {**HEADERS, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read(), strict=False)
    except urllib.error.HTTPError as e:
        if e.code in (429, 503):  # submission still pending or capacity full: resend with the same key
            return {}
        raise


def main(session_id: str, query: str) -> None:
    key = str(uuid.uuid4())  # one key per request; resending it never starts a second run
    while not (sub := call(BASE, {"query": query, "session_id": session_id}, {"Idempotency-Key": key})):
        time.sleep(10)
    execution_id = sub.get("execution_id") or sub["execution"]["execution_id"]
    while (e := call(f"{BASE}/{execution_id}")["execution"])["status"] not in ("completed", "failed", "cancelled"):
        time.sleep(15)
    if e["status"] != "completed":
        sys.exit(f"{e['status']}: {e['error']}")
    print(e["result"]["pi"]["messages"][0]["content"][0]["text"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
