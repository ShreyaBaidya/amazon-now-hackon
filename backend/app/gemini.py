"""Unified HTTP LLM client — supports Groq (OpenAI-compatible) and Google Gemini.

Priority: Groq > Gemini. Set GROQ_API_KEY or GEMINI_API_KEY in .env.
Same interface as bedrock.run_tools()
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

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def available() -> bool:
    return bool(GROQ_KEY) or bool(GEMINI_KEY)


# ── convert Bedrock-format messages ──────────────────────────────────────

def _to_openai_msgs(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = "assistant" if m["role"] == "assistant" else "user"
        text_parts = []
        tool_calls = []
        has_tool_result = False
        for c in m.get("content", []):
            if "text" in c:
                text_parts.append(c["text"])
            if "toolUse" in c:
                tu = c["toolUse"]
                tool_calls.append({
                    "id": tu.get("toolUseId", tu["name"]),
                    "type": "function",
                    "function": {
                        "name": tu["name"],
                        "arguments": json.dumps(tu.get("input", {})),
                    },
                })
            if "toolResult" in c:
                has_tool_result = True
                tr = c["toolResult"]
                resp = {}
                for tc in tr.get("content", []):
                    if "json" in tc:
                        resp = tc["json"]
                out.append({
                    "role": "tool",
                    "tool_call_id": tr.get("toolUseId", ""),
                    "content": json.dumps(resp),
                })
        entry = {"role": role}
        if text_parts:
            entry["content"] = "\n".join(text_parts)
        if tool_calls:
            entry["tool_calls"] = tool_calls
            if not text_parts:
                entry["content"] = None
        if role != "user" or (text_parts or tool_calls):
            out.append(entry)
        elif has_tool_result:
            pass
    return out


def _to_gemini_msgs(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        parts = []
        for c in m.get("content", []):
            if "text" in c:
                parts.append({"text": c["text"]})
            if "toolUse" in c:
                tu = c["toolUse"]
                parts.append({
                    "functionCall": {"name": tu["name"], "args": tu.get("input", {})}
                })
            if "toolResult" in c:
                tr = c["toolResult"]
                resp = {}
                for tc in tr.get("content", []):
                    if "json" in tc:
                        resp = tc["json"]
                parts.append({
                    "functionResponse": {
                        "name": tr["toolUseId"],
                        "response": {"name": tr["toolUseId"], "content": resp},
                    }
                })
        if parts:
            out.append({"role": role, "parts": parts})
    return out


# ── convert Bedrock-format tools ────────────────────────────────────────

def _to_openai_tools(tools: list[dict]) -> list[dict]:
    out = []
    for t in tools:
        spec = t.get("toolSpec", {})
        out.append({
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "parameters": spec.get("inputSchema", {}).get("json", {}),
            },
        })
    return out


def _to_gemini_tools(tools: list[dict]) -> list[dict]:
    out = []
    for t in tools:
        spec = t.get("toolSpec", {})
        out.append({
            "functionDeclarations": [{
                "name": spec["name"],
                "description": spec.get("description", ""),
                "parameters": spec.get("inputSchema", {}).get("json", {}),
            }]
        })
    return out


# ── main loop ────────────────────────────────────────────────────────────

def run_tools(messages: list[dict], system: str, tools: list[dict],
              handlers: dict, max_calls: int = 10) -> tuple[list[dict], int]:
    use_groq = bool(GROQ_KEY)
    use_gemini = not use_groq and bool(GEMINI_KEY)

    if not use_groq and not use_gemini:
        raise RuntimeError("neither GROQ_API_KEY nor GEMINI_API_KEY is set")

    if use_groq:
        url = "https://api.groq.com/openai/v1/chat/completions"
        api_key = GROQ_KEY
        model = GROQ_MODEL
        convert_msgs = _to_openai_msgs
        convert_tools = _to_openai_tools
    else:
        url = f"https://generativelanguage.googleapis.com/v1alpha/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
        api_key = ""
        model = GEMINI_MODEL
        convert_msgs = _to_gemini_msgs
        convert_tools = _to_gemini_tools

    calls = 0

    while calls < max_calls:
        if use_groq:
            msgs = convert_msgs(messages)
            if system:
                msgs.insert(0, {"role": "system", "content": system})
            body = {
                "model": model,
                "messages": msgs,
                "tools": convert_tools(tools) if tools else None,
            }
        else:
            body = {
                "contents": convert_msgs(messages),
                "tools": convert_tools(tools),
            }
            if system:
                body["systemInstruction"] = {"parts": [{"text": system}]}

        headers = {"Content-Type": "application/json", "User-Agent": "amznow/1.0"}
        if use_groq:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            raise RuntimeError(f"API error {e.code}: {err_body}") from e

        if use_groq:
            choice = raw.get("choices", [{}])[0]
            msg = choice.get("message", {})
            finish = choice.get("finish_reason", "")
            text = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []
        else:
            candidate = raw.get("candidates", [{}])[0]
            parts = candidate.get("content", {}).get("parts", [])
            finish = candidate.get("finishReason", "")
            text = ""
            tool_calls = []
            for p in parts:
                if "text" in p:
                    text += p["text"]
                if "functionCall" in p:
                    fc = p["functionCall"]
                    tool_calls.append({
                        "id": fc["name"],
                        "function": {"name": fc["name"], "arguments": json.dumps(fc.get("args", {}))},
                    })

        out_content = []
        if text:
            out_content.append({"text": text})
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
            out_content.append({
                "toolUse": {
                    "toolUseId": tc.get("id", fn_name),
                    "name": fn_name,
                    "input": fn_args,
                }
            })

        messages.append({"role": "assistant", "content": out_content})

        if finish == "stop" and not tool_calls:
            break
        if finish == "STOP" and not tool_calls:
            break
        if not tool_calls:
            break

        results = []
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
            calls += 1
            fn = handlers.get(fn_name)
            try:
                payload = fn(fn_args) if fn else {"error": "unknown tool"}
            except Exception as e:
                payload = {"error": str(e)}
            results.append({
                "toolResult": {
                    "toolUseId": tc.get("id", fn_name),
                    "content": [{"json": payload}],
                }
            })
        messages.append({"role": "user", "content": results})

    return messages, calls
