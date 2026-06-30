"""Amazon Bedrock client — minimal Converse wrapper.

Region + model are env-overridable. Default = Nova Lite via the APAC
inference profile (ap-south-1 requires an inference-profile id, not a raw
model id). Access is granted on the account; calls may be daily-throttled
on free tier.
"""
from __future__ import annotations

import os
from pathlib import Path

import boto3


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines without overriding variables already exported."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


ROOT = Path(__file__).resolve().parents[2]
for env_path in (ROOT / ".env", ROOT / ".env.local", ROOT / "backend" / ".env",
                 ROOT / "backend" / ".env.local"):
    _load_env_file(env_path)

REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "zai.glm-4.7-flash")

_client = None


def available() -> bool:
    """Check if Bedrock is accessible. Returns True even when throttled (daily
    quota exhausted) — the runner loop will try and fail gracefully."""
    try:
        c = client()
        c.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": "ping"}]}],
            inferenceConfig={"maxTokens": 2},
        )
        return True
    except Exception as e:
        err = str(e)
        # Throttling = configured but rate-limited; still return True so the
        # runner tries it. Credential/AccessDenied = not usable.
        if "Throttling" in err or "Too many tokens" in err:
            return True
        return False


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=REGION)
    return _client


def converse(messages: list[dict], system: str | None = None,
             tools: list[dict] | None = None, **kw) -> dict:
    """Thin pass-through to Bedrock Converse. Returns the raw response dict."""
    args: dict = {"modelId": MODEL_ID, "messages": messages}
    if system:
        args["system"] = [{"text": system}]
    if tools:
        args["toolConfig"] = {"tools": tools}
    args.update(kw)
    return client().converse(**args)


def run_tools(messages: list[dict], system: str, tools: list[dict],
              handlers: dict, max_calls: int = 10) -> tuple[list[dict], int]:
    """Drive a tool-use loop. Appends turns to `messages` in place, runs each
    requested tool via `handlers[name](input)`, feeds results back. Returns
    (messages, tool_call_count). Stops when the model stops asking for tools
    or the call budget is hit."""
    calls = 0
    while calls < max_calls:
        resp = converse(messages, system=system, tools=tools)
        out = resp["output"]["message"]
        messages.append(out)
        uses = [b["toolUse"] for b in out.get("content", []) if "toolUse" in b]
        if resp.get("stopReason") != "tool_use" or not uses:
            break
        results = []
        for u in uses:
            calls += 1
            fn = handlers.get(u["name"])
            try:
                payload = fn(u.get("input") or {}) if fn else {"error": "unknown tool"}
            except Exception as e:  # noqa: BLE001 — surface tool failure to model
                payload = {"error": str(e)}
            results.append({"toolResult": {"toolUseId": u["toolUseId"],
                                           "content": [{"document": payload}]}})
        messages.append({"role": "user", "content": results})
    return messages, calls


def stream_text(messages: list[dict], system: str | None = None):
    """Yield reply text chunks from ConverseStream (final answer, no tools)."""
    args: dict = {"modelId": MODEL_ID, "messages": messages}
    if system:
        args["system"] = [{"text": system}]
    resp = client().converse_stream(**args)
    for ev in resp["stream"]:
        delta = ev.get("contentBlockDelta", {}).get("delta", {})
        if "text" in delta:
            yield delta["text"]


def ping(prompt: str = "Reply with just the word OK.") -> dict:
    """Connectivity probe: one round-trip, returns text + token usage."""
    resp = converse([{"role": "user", "content": [{"text": prompt}]}])
    text = resp["output"]["message"]["content"][0]["text"]
    usage = resp.get("usage", {})
    return {
        "ok": True,
        "region": REGION,
        "model_id": MODEL_ID,
        "text": text,
        "usage": usage,
    }
