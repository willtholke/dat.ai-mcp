"""dat.ai Hermes plugin - registers browser automation, transcription, and LLM chat tools."""

import asyncio
import base64
import json
import os
import urllib.parse

import httpx

from hermes_cli.plugins import PluginContext

BASE_URL = "https://llm.dat.ai"
DEFAULT_TIMEOUT = 600.0


def _get_api_key() -> str:
    key = os.environ.get("DAT_AI_API_KEY")
    if not key:
        raise RuntimeError(
            "DAT_AI_API_KEY environment variable is required. "
            "Get your API key at https://dat.ai/"
        )
    return key


async def _dat_request(
    path: str,
    method: str = "GET",
    headers: dict | None = None,
    content: bytes | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict | str:
    api_key = _get_api_key()
    req_headers = {"Authorization": f"Bearer {api_key}"}
    if headers:
        req_headers.update(headers)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method, f"{BASE_URL}{path}", headers=req_headers, content=content
        )
        text = response.text
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
        if response.status_code >= 400:
            if isinstance(data, dict) and "error" in data:
                err = data["error"]
                msg = err if isinstance(err, str) else err.get("message", json.dumps(err))
            else:
                msg = f"HTTP {response.status_code}: {text}"
            raise RuntimeError(msg)
        return data


# --- Tool schemas (JSON) ---

_TOOL_SCHEMAS = {
    "dat_browse": {
        "name": "dat_browse",
        "description": (
            "Run a browser automation task on dat.ai. Give a natural language "
            "instruction and dat.ai will drive a real browser to complete it. "
            "Returns the result and any screenshot URLs. Uses sync mode by "
            "default (waits up to 10 min). Set async_mode=true to get a task_id "
            "immediately and poll with dat_browse_status."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The instruction to execute in the browser"},
                "async_mode": {"type": "boolean", "default": False, "description": "Return task_id immediately instead of waiting"},
                "screenshots_mode": {"type": "string", "enum": ["final_only", "every_step", "on_navigation"], "description": "Screenshot capture mode"},
                "full_page": {"type": "boolean", "default": True, "description": "Capture full scrollable page (final_only mode)"},
                "country_iso": {"type": "string", "description": "Route to browsing nodes in this country (ISO code)"},
                "session_key": {"type": "string", "description": "Group browsing tasks into a shared session"},
                "timeout": {"type": "integer", "description": "Task timeout in milliseconds (max 3 hours)"},
                "fanout": {"type": "integer", "description": "Number of nodes to race the task on (1-10)"},
            },
            "required": ["task"],
        },
    },
    "dat_browse_status": {
        "name": "dat_browse_status",
        "description": "Check the status of an async dat.ai browsing task.",
        "parameters": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "The task_id from dat_browse with async_mode=true"}},
            "required": ["task_id"],
        },
    },
    "dat_browse_screenshot": {
        "name": "dat_browse_screenshot",
        "description": "Download a screenshot from a completed dat.ai browsing task. Returns base64 image data.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The browsing task ID"},
                "filename": {"type": "string", "description": "Screenshot filename, e.g. 'screenshot-01.png'"},
            },
            "required": ["task_id", "filename"],
        },
    },
    "dat_transcribe": {
        "name": "dat_transcribe",
        "description": "Transcribe audio to text using dat.ai Whisper API. Accepts audio URL or base64 data.",
        "parameters": {
            "type": "object",
            "properties": {
                "audio_url": {"type": "string", "description": "URL of the audio file to transcribe"},
                "audio_base64": {"type": "string", "description": "Base64-encoded audio data"},
                "content_type": {"type": "string", "default": "audio/wav", "description": "Content-Type of audio when using audio_base64"},
                "async_mode": {"type": "boolean", "default": False, "description": "Return task_id immediately"},
            },
        },
    },
    "dat_transcribe_status": {
        "name": "dat_transcribe_status",
        "description": "Check the status of an async dat.ai transcription task.",
        "parameters": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "The task_id from dat_transcribe with async_mode=true"}},
            "required": ["task_id"],
        },
    },
    "dat_completions": {
        "name": "dat_completions",
        "description": "OpenAI-compatible chat completions via dat.ai. Supports streaming, function calling, and built-in tools (net/fs/webview).",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name, e.g. 'qwen3:1.7b'"},
                "messages": {"type": "array", "items": {"type": "object", "properties": {"role": {"type": "string"}, "content": {"type": "string"}}, "required": ["role", "content"]}, "description": "Chat messages"},
                "stream": {"type": "boolean", "default": False, "description": "Enable streaming"},
                "max_tokens": {"type": "integer"},
                "temperature": {"type": "number"},
                "top_p": {"type": "number"},
                "stop": {"type": "string"},
                "seed": {"type": "integer"},
                "tools": {"type": "array"},
                "tool_choice": {"type": "string"},
                "datai_tools": {"type": "object", "properties": {"net": {"type": "boolean"}, "fs": {"type": "boolean"}, "webview": {"type": "boolean"}}, "description": "dat.ai built-in tools. Cannot be used with stream=true."},
            },
            "required": ["model", "messages"],
        },
    },
    "dat_chat": {
        "name": "dat_chat",
        "description": "Ollama-compatible chat endpoint via dat.ai. NDJSON streaming, system prompts, built-in tools.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name, e.g. 'qwen3:1.7b'"},
                "messages": {"type": "array", "items": {"type": "object", "properties": {"role": {"type": "string"}, "content": {"type": "string"}}, "required": ["role", "content"]}, "description": "Chat messages"},
                "system": {"type": "string", "description": "System prompt"},
                "stream": {"type": "boolean", "default": False, "description": "Enable NDJSON streaming"},
                "options": {"type": "object", "description": "Ollama options (temperature, top_p, etc.)"},
                "datai_tools": {"type": "object", "properties": {"net": {"type": "boolean"}, "fs": {"type": "boolean"}, "webview": {"type": "boolean"}}, "description": "dat.ai built-in tools. Cannot be used with stream=true."},
            },
            "required": ["model", "messages"],
        },
    },
}


# --- Tool handlers ---

def _dat_browse(args: dict, **_kw) -> str:
    body: dict = {"task": args["task"]}
    mode = args.get("screenshots_mode")
    if mode:
        body["screenshots"] = {"mode": mode, "full_page": args.get("full_page", True)}
    if args.get("country_iso"):
        body["filter"] = {"country_iso": args["country_iso"]}
    for k in ("session_key", "timeout", "fanout"):
        if args.get(k):
            body[k] = args[k]
    endpoint = "/api/v1/browsing/async" if args.get("async_mode") else "/api/v1/browsing/sync"
    result = asyncio.run(_dat_request(endpoint, "POST", {"Content-Type": "application/json"}, json.dumps(body)))
    return json.dumps(result, indent=2)


def _dat_browse_status(args: dict, **_kw) -> str:
    tid = urllib.parse.quote(args["task_id"])
    result = asyncio.run(_dat_request(f"/api/v1/browsing/status?task_id={tid}"))
    return json.dumps(result, indent=2)


def _dat_browse_screenshot(args: dict, **_kw) -> str:
    api_key = _get_api_key()
    tid = urllib.parse.quote(args["task_id"])
    fn = urllib.parse.quote(args["filename"])
    url = f"{BASE_URL}/api/v1/browsing/screenshots/{tid}/{fn}"

    async def _fetch():
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            return r

    r = asyncio.run(_fetch())
    img_b64 = base64.b64encode(r.content).decode()
    return json.dumps({"image": img_b64, "mimeType": r.headers.get("content-type", "image/png")})


def _dat_transcribe(args: dict, **_kw) -> str:
    endpoint = "/api/whisper/transcribe/async" if args.get("async_mode") else "/api/whisper/transcribe/sync"
    ct = args.get("content_type", "audio/wav")

    async def _do():
        if args.get("audio_url"):
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                ar = await client.get(args["audio_url"])
                ar.raise_for_status()
                audio = ar.content
                ct_actual = ct or ar.headers.get("content-type", "audio/wav")
            return await _dat_request(endpoint, "POST", {"Content-Type": ct_actual}, audio)
        elif args.get("audio_base64"):
            audio = base64.b64decode(args["audio_base64"])
            return await _dat_request(endpoint, "POST", {"Content-Type": ct}, audio)
        raise ValueError("Either audio_url or audio_base64 is required")

    result = asyncio.run(_do())
    return json.dumps(result, indent=2)


def _dat_transcribe_status(args: dict, **_kw) -> str:
    tid = urllib.parse.quote(args["task_id"])
    result = asyncio.run(_dat_request(f"/api/whisper/transcribe/status?task_id={tid}"))
    return json.dumps(result, indent=2)


def _dat_completions(args: dict, **_kw) -> str:
    stream = args.get("stream", False)
    datai_tools = args.get("datai_tools")
    if stream and datai_tools:
        raise ValueError("Tools cannot be used with streaming")

    body: dict = {"model": args["model"], "messages": args["messages"], "stream": stream}
    for f in ("max_tokens", "temperature", "top_p", "stop", "seed", "tools", "tool_choice"):
        if args.get(f) is not None:
            body[f] = args[f]
    if datai_tools:
        body["datai"] = {"tools": datai_tools}

    if stream:
        async def _stream():
            api_key = _get_api_key()
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                r = await client.post(f"{BASE_URL}/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body)
                r.raise_for_status()
                content = ""
                for line in r.text.split("\n"):
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        if delta:
                            content += delta
                    except json.JSONDecodeError:
                        pass
                return content or "(empty response)"
        return asyncio.run(_stream())

    result = asyncio.run(_dat_request("/v1/chat/completions", "POST", {"Content-Type": "application/json"}, json.dumps(body)))
    return json.dumps(result, indent=2)


def _dat_chat(args: dict, **_kw) -> str:
    stream = args.get("stream", False)
    datai_tools = args.get("datai_tools")
    if stream and datai_tools:
        raise ValueError("Tools cannot be used with streaming")

    body: dict = {"model": args["model"], "messages": args["messages"], "stream": stream}
    if args.get("system"):
        body["system"] = args["system"]
    if args.get("options"):
        body["options"] = args["options"]
    if datai_tools:
        body["datai"] = {"tools": datai_tools}

    if stream:
        async def _stream():
            api_key = _get_api_key()
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                r = await client.post(f"{BASE_URL}/api/chat", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body)
                r.raise_for_status()
                content = ""
                for line in r.text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if chunk.get("error"):
                            raise RuntimeError(chunk["error"])
                        msg = chunk.get("message", {})
                        if msg.get("content"):
                            content += msg["content"]
                    except json.JSONDecodeError:
                        pass
                return content or "(empty response)"
        return asyncio.run(_stream())

    result = asyncio.run(_dat_request("/api/chat", "POST", {"Content-Type": "application/json"}, json.dumps(body)))
    return json.dumps(result, indent=2)


_HANDLERS = {
    "dat_browse": _dat_browse,
    "dat_browse_status": _dat_browse_status,
    "dat_browse_screenshot": _dat_browse_screenshot,
    "dat_transcribe": _dat_transcribe,
    "dat_transcribe_status": _dat_transcribe_status,
    "dat_completions": _dat_completions,
    "dat_chat": _dat_chat,
}


def register(ctx: PluginContext) -> None:
    """Register dat.ai tools with the Hermes plugin manager."""
    for name, schema in _TOOL_SCHEMAS.items():
        handler = _HANDLERS[name]
        ctx.register_tool(
            name=name,
            toolset="dat-ai",
            schema=schema,
            handler=lambda args, _h=handler, **kw: _h(args or {}, **kw),
            check_fn=lambda _k=os.environ.get("DAT_AI_API_KEY"): bool(_k),
            requires_env=["DAT_AI_API_KEY"],
        )