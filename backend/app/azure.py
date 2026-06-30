"""Azure OpenAI Responses API client — drop-in for tool-use loop.

Set AZURE_API_KEY and AZURE_ENDPOINT in .env.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path


def _load_env_file(path: Path) -> None:
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

API_KEY = os.environ.get("AZURE_API_KEY", "")
ENDPOINT = os.environ.get("AZURE_ENDPOINT", "")
MODEL = os.environ.get("AZURE_MODEL", "gpt-5-mini")


def available() -> bool:
    return bool(API_KEY) and bool(ENDPOINT)


def _add_strict(s: dict) -> dict:
    if s.get("type") == "object":
        s["additionalProperties"] = False
        props = s.get("properties", {})
        s["required"] = list(props.keys())
        for v in props.values():
            _add_strict(v)
    if s.get("type") == "array" and "items" in s:
        _add_strict(s["items"])
    return s


def _convert_tools(tools: list[dict]) -> list[dict]:
    out = []
    for t in tools:
        spec = t.get("toolSpec", {})
        schema = spec.get("inputSchema", {}).get("json", {})
        _add_strict(schema)
        out.append({
            "type": "function",
            "name": spec["name"],
            "description": spec.get("description", ""),
            "strict": True,
            "parameters": schema,
        })
    return out


def _call(body: dict) -> dict:
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"api-key": API_KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"Azure API error {e.code}: {err_body}") from e


def run_tools(messages: list[dict], system: str, tools: list[dict],
              handlers: dict, max_calls: int = 10) -> tuple[list[dict], int]:
    if not API_KEY:
        raise RuntimeError("AZURE_API_KEY not set")

    # Extract user text from the first message
    user_text = ""
    for m in messages:
        if m["role"] == "user":
            for c in m.get("content", []):
                if "text" in c:
                    user_text += c["text"]

    calls = 0
    prev_id = None
    tool_inputs: list[dict] = []

    while calls < max_calls:
        body: dict = {
            "model": MODEL,
            "input": tool_inputs if prev_id else user_text,
            "max_output_tokens": 2048,
            "reasoning": {"effort": "low"},
            "tools": _convert_tools(tools),
        }
        if system:
            body["instructions"] = system
        if prev_id:
            body["previous_response_id"] = prev_id

        raw = _call(body)
        print(f"[Azure] call#{calls} status={raw.get('status')} output_types={[o.get('type') for o in raw.get('output',[])]}", flush=True)
        prev_id = raw.get("id")
        status = raw.get("status", "")
        output_items = raw.get("output", [])

        # Build assistant content
        text_parts = []
        fcs = []

        for item in output_items:
            t = item.get("type")
            if t == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        text_parts.append(c.get("text", ""))
            elif t == "function_call":
                args = item.get("arguments", "{}")
                if isinstance(args, str):
                    args = json.loads(args)
                fcs.append({
                    "toolUse": {
                        "toolUseId": item["call_id"],
                        "name": item["name"],
                        "input": args,
                    }
                })
            elif t == "reasoning":
                pass

        out_content = []
        if text_parts:
            out_content.append({"text": "".join(text_parts)})
        for fc in fcs:
            out_content.append(fc)

        messages.append({"role": "assistant", "content": out_content})

        if status == "completed" and not fcs:
            break
        if not fcs:
            break

        # Execute tools and build next input
        tool_inputs = []
        for fc in fcs:
            tu = fc["toolUse"]
            calls += 1
            fn = handlers.get(tu["name"])
            try:
                payload = fn(tu.get("input", {})) if fn else {"error": "unknown tool"}
            except Exception as e:
                payload = {"error": str(e)}
            tool_inputs.append({
                "type": "function_call_output",
                "call_id": tu["toolUseId"],
                "output": json.dumps(payload),
            })
            messages.append({
                "role": "user",
                "content": [{"toolResult": {
                    "toolUseId": tu["toolUseId"],
                    "content": [{"json": payload}],
                }}]
            })

    return messages, calls


def _messages_to_azure_input(messages: list[dict]) -> list[dict]:
    """Convert Bedrock-format messages (text + image) to Azure Responses API input array."""
    import base64
    azure_msgs = []
    for m in messages:
        items = []
        for c in m.get("content", []):
            if "text" in c:
                items.append({"type": "input_text", "text": c["text"]})
            elif "image" in c:
                img = c["image"]
                fmt = img.get("format", "jpeg")
                source = img.get("source", {})
                if "bytes" in source:
                    b64 = base64.b64encode(source["bytes"]).decode()
                    items.append({
                        "type": "input_image",
                        "image_url": f"data:image/{fmt};base64,{b64}"
                    })
        if items:
            azure_msgs.append({"role": m["role"], "content": items})
    return azure_msgs


def converse(messages: list[dict], system: str | None = None) -> dict:
    """Match bedrock.converse signature — supports text + image input."""
    body: dict = {
        "model": MODEL,
        "input": _messages_to_azure_input(messages),
        "max_output_tokens": 2048,
        "reasoning": {"effort": "low"},
    }
    if system:
        body["instructions"] = system

    raw = _call(body)

    text_parts = []
    for item in raw.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    text_parts.append(c.get("text", ""))

    return {
        "output": {
            "message": {
                "content": [{"text": "".join(text_parts)}]
            }
        }
    }
