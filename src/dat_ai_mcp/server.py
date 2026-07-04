"""MCP server for the dat.ai API."""

import base64
import json
import os
import sys

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

BASE_URL = "https://llm.dat.ai"
DEFAULT_TIMEOUT = 600.0


def get_api_key() -> str:
    key = os.environ.get("DAT_AI_API_KEY")
    if not key:
        raise ValueError(
            "DAT_AI_API_KEY environment variable is required. "
            "Get your API key at https://dat.ai/"
        )
    return key


async def dat_request(
    path: str,
    method: str = "GET",
    headers: dict | None = None,
    content: bytes | str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict | str:
    api_key = get_api_key()
    req_headers = {"Authorization": f"Bearer {api_key}"}
    if headers:
        req_headers.update(headers)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            f"{BASE_URL}{path}",
            headers=req_headers,
            content=content,
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


# --- Tool schemas ---

TOOLS = [
    types.Tool(
        name="dat_browse",
        description=(
            "Run a browser automation task on dat.ai. Give a natural language "
            "instruction and dat.ai will drive a real browser to complete it. "
            "Returns the result and any screenshot URLs. Uses sync mode by "
            "default (waits for completion, up to 10 min). Set async_mode=true "
            "to get a task_id immediately and poll with dat_browse_status."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "The instruction to execute in the browser, e.g. "
                        "'Open https://example.com and summarize the page'"
                    ),
                },
                "async_mode": {
                    "type": "boolean",
                    "description": (
                        "If true, return a task_id immediately instead of waiting. "
                        "Poll with dat_browse_status. Default: false"
                    ),
                    "default": False,
                },
                "screenshots_mode": {
                    "type": "string",
                    "enum": ["final_only", "every_step", "on_navigation"],
                    "description": (
                        "Screenshot capture mode. final_only: one screenshot after "
                        "completion. every_step: screenshot each step. on_navigation: "
                        "screenshot on URL change. Default: none (no screenshots)."
                    ),
                },
                "full_page": {
                    "type": "boolean",
                    "description": (
                        "Used by final_only mode. Capture full scrollable page. "
                        "Default: true."
                    ),
                    "default": True,
                },
                "country_iso": {
                    "type": "string",
                    "description": (
                        "Route to browsing nodes in this country (ISO code, "
                        "e.g. 'US', 'DE'). Optional."
                    ),
                },
                "session_key": {
                    "type": "string",
                    "description": "Group browsing tasks into a shared session. Optional.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Task timeout in milliseconds (max 10800000 = 3 hours). Optional.",
                },
                "fanout": {
                    "type": "integer",
                    "description": "Number of nodes to race the task on (1-10, default 1). Optional.",
                },
            },
            "required": ["task"],
        },
    ),
    types.Tool(
        name="dat_browse_status",
        description=(
            "Check the status of an async dat.ai browsing task. Returns status "
            "(queued/assigned/running/completed/failed) and result if ready."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task_id returned from dat_browse with async_mode=true.",
                },
            },
            "required": ["task_id"],
        },
    ),
    types.Tool(
        name="dat_browse_screenshot",
        description=(
            "Download a screenshot from a completed dat.ai browsing task. "
            "Returns the image as base64 data."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The browsing task ID.",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "The screenshot filename, e.g. 'screenshot-01.png'. "
                        "Get filenames from the browsing result."
                    ),
                },
            },
            "required": ["task_id", "filename"],
        },
    ),
    types.Tool(
        name="dat_transcribe",
        description=(
            "Transcribe audio to text using dat.ai's Whisper API. Provide audio "
            "as a URL (the server will fetch it) or as base64-encoded data. "
            "Returns transcribed text. Uses sync mode (waits for completion, up to 10 min)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "audio_url": {
                    "type": "string",
                    "description": "URL of the audio file to transcribe. The server will download and transcribe it.",
                },
                "audio_base64": {
                    "type": "string",
                    "description": "Base64-encoded audio data. Will be sent as raw bytes.",
                },
                "content_type": {
                    "type": "string",
                    "description": (
                        "Content-Type of the audio when using audio_base64, "
                        "e.g. 'audio/wav', 'audio/mpeg', 'audio/mp4'. "
                        "Default: 'audio/wav'."
                    ),
                    "default": "audio/wav",
                },
                "async_mode": {
                    "type": "boolean",
                    "description": "If true, return a task_id immediately. Poll with dat_transcribe_status. Default: false.",
                    "default": False,
                },
            },
        },
    ),
    types.Tool(
        name="dat_transcribe_status",
        description="Check the status of an async dat.ai transcription task.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task_id returned from dat_transcribe with async_mode=true.",
                },
            },
            "required": ["task_id"],
        },
    ),
    types.Tool(
        name="dat_completions",
        description=(
            "OpenAI-compatible chat completions via dat.ai. Supports streaming "
            "and non-streaming. Can enable built-in tools (net, fs, webview) via "
            "the datai_tools parameter. Note: tools cannot be used with streaming."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name, e.g. 'qwen3:1.7b'"},
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["system", "user", "assistant", "tool"]},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                    "description": "Chat messages array.",
                },
                "stream": {
                    "type": "boolean",
                    "description": "Enable streaming. Default: false.",
                    "default": False,
                },
                "max_tokens": {"type": "integer", "description": "Maximum tokens to generate. Optional."},
                "temperature": {"type": "number", "description": "Sampling temperature. Optional."},
                "top_p": {"type": "number", "description": "Nucleus sampling parameter. Optional."},
                "stop": {"type": "string", "description": "Stop sequence(s). Optional."},
                "seed": {"type": "integer", "description": "Random seed. Optional."},
                "tools": {"type": "array", "description": "OpenAI function-calling tools. Optional."},
                "tool_choice": {"type": "string", "description": "Tool choice strategy. Optional."},
                "datai_tools": {
                    "type": "object",
                    "properties": {
                        "net": {"type": "boolean", "description": "Enable network/HTTP tools."},
                        "fs": {"type": "boolean", "description": "Enable filesystem tools."},
                        "webview": {"type": "boolean", "description": "Enable browser/webview tools."},
                    },
                    "description": "dat.ai built-in tools. Cannot be used with stream=true.",
                },
            },
            "required": ["model", "messages"],
        },
    ),
    types.Tool(
        name="dat_chat",
        description=(
            "Ollama-compatible chat endpoint via dat.ai. Supports NDJSON streaming "
            "and non-streaming. Can enable built-in tools (net, fs, webview). "
            "Note: tools cannot be used with streaming."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name, e.g. 'qwen3:1.7b'"},
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["system", "user", "assistant", "tool"]},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                    "description": "Chat messages array.",
                },
                "system": {"type": "string", "description": "System prompt. Optional."},
                "stream": {
                    "type": "boolean",
                    "description": "Enable NDJSON streaming. Default: false.",
                    "default": False,
                },
                "options": {
                    "type": "object",
                    "description": "Ollama options (temperature, top_p, top_k, num_predict, num_ctx, stop, seed). Optional.",
                },
                "datai_tools": {
                    "type": "object",
                    "properties": {
                        "net": {"type": "boolean", "description": "Enable network/HTTP tools."},
                        "fs": {"type": "boolean", "description": "Enable filesystem tools."},
                        "webview": {"type": "boolean", "description": "Enable browser/webview tools."},
                    },
                    "description": "dat.ai built-in tools. Cannot be used with stream=true.",
                },
            },
            "required": ["model", "messages"],
        },
    ),
]


# --- Tool handlers ---

async def handle_dat_browse(args: dict) -> list[types.TextContent]:
    body: dict = {"task": args["task"]}
    screenshots_mode = args.get("screenshots_mode")
    if screenshots_mode:
        body["screenshots"] = {"mode": screenshots_mode, "full_page": args.get("full_page", True)}
    country_iso = args.get("country_iso")
    if country_iso:
        body["filter"] = {"country_iso": country_iso}
    if args.get("session_key"):
        body["session_key"] = args["session_key"]
    if args.get("timeout"):
        body["timeout"] = args["timeout"]
    if args.get("fanout"):
        body["fanout"] = args["fanout"]

    endpoint = "/api/v1/browsing/async" if args.get("async_mode") else "/api/v1/browsing/sync"
    result = await dat_request(endpoint, method="POST", headers={"Content-Type": "application/json"}, content=json.dumps(body))
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_dat_browse_status(args: dict) -> list[types.TextContent]:
    import urllib.parse
    task_id = urllib.parse.quote(args["task_id"])
    result = await dat_request(f"/api/v1/browsing/status?task_id={task_id}")
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_dat_browse_screenshot(args: dict) -> list[types.ImageContent]:
    import urllib.parse
    api_key = get_api_key()
    task_id = urllib.parse.quote(args["task_id"])
    filename = urllib.parse.quote(args["filename"])
    url = f"{BASE_URL}/api/v1/browsing/screenshots/{task_id}/{filename}"

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()

    img_b64 = base64.b64encode(response.content).decode()
    content_type = response.headers.get("content-type", "image/png")
    return [types.ImageContent(type="image", data=img_b64, mimeType=content_type)]


async def handle_dat_transcribe(args: dict) -> list[types.TextContent]:
    endpoint = "/api/whisper/transcribe/async" if args.get("async_mode") else "/api/whisper/transcribe/sync"
    audio_url = args.get("audio_url")
    audio_base64 = args.get("audio_base64")
    content_type = args.get("content_type", "audio/wav")

    if audio_url:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            audio_response = await client.get(audio_url)
            audio_response.raise_for_status()
        audio_bytes = audio_response.content
        ct = content_type or audio_response.headers.get("content-type", "audio/wav")
        result = await dat_request(endpoint, method="POST", headers={"Content-Type": ct}, content=audio_bytes)
    elif audio_base64:
        audio_bytes = base64.b64decode(audio_base64)
        result = await dat_request(endpoint, method="POST", headers={"Content-Type": content_type}, content=audio_bytes)
    else:
        raise ValueError("Either audio_url or audio_base64 is required")

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_dat_transcribe_status(args: dict) -> list[types.TextContent]:
    import urllib.parse
    task_id = urllib.parse.quote(args["task_id"])
    result = await dat_request(f"/api/whisper/transcribe/status?task_id={task_id}")
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_dat_completions(args: dict) -> list[types.TextContent]:
    stream = args.get("stream", False)
    datai_tools = args.get("datai_tools")

    if stream and datai_tools:
        raise ValueError("Tools cannot be used with streaming (dat.ai returns 400 for this combination)")

    body: dict = {
        "model": args["model"],
        "messages": args["messages"],
        "stream": stream,
    }
    for field in ("max_tokens", "temperature", "top_p", "stop", "seed", "tools", "tool_choice"):
        if args.get(field) is not None:
            body[field] = args[field]
    if datai_tools:
        body["datai"] = {"tools": datai_tools}

    if stream:
        api_key = get_api_key()
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{BASE_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            full_content = ""
            for line in response.text.split("\n"):
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        full_content += delta
                except json.JSONDecodeError:
                    pass
        return [types.TextContent(type="text", text=full_content or "(empty response)")]

    result = await dat_request(
        "/v1/chat/completions",
        method="POST",
        headers={"Content-Type": "application/json"},
        content=json.dumps(body),
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_dat_chat(args: dict) -> list[types.TextContent]:
    stream = args.get("stream", False)
    datai_tools = args.get("datai_tools")

    if stream and datai_tools:
        raise ValueError("Tools cannot be used with streaming (dat.ai returns 400 for this combination)")

    body: dict = {
        "model": args["model"],
        "messages": args["messages"],
        "stream": stream,
    }
    if args.get("system"):
        body["system"] = args["system"]
    if args.get("options"):
        body["options"] = args["options"]
    if datai_tools:
        body["datai"] = {"tools": datai_tools}

    if stream:
        api_key = get_api_key()
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(
                f"{BASE_URL}/api/chat",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
            full_content = ""
            for line in response.text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise RuntimeError(chunk["error"])
                    msg = chunk.get("message", {})
                    if msg.get("content"):
                        full_content += msg["content"]
                except json.JSONDecodeError:
                    pass
        return [types.TextContent(type="text", text=full_content or "(empty response)")]

    result = await dat_request(
        "/api/chat",
        method="POST",
        headers={"Content-Type": "application/json"},
        content=json.dumps(body),
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


# --- Server ---

server = Server("dat-ai-mcp")

HANDLERS = {
    "dat_browse": handle_dat_browse,
    "dat_browse_status": handle_dat_browse_status,
    "dat_browse_screenshot": handle_dat_browse_screenshot,
    "dat_transcribe": handle_dat_transcribe,
    "dat_transcribe_status": handle_dat_transcribe_status,
    "dat_completions": handle_dat_completions,
    "dat_chat": handle_dat_chat,
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list:
    handler = HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    try:
        return await handler(arguments or {})
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())