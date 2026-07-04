#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const BASE_URL = "https://llm.dat.ai";

function getApiKey(): string {
  const key = process.env.DAT_AI_API_KEY;
  if (!key) {
    throw new Error(
      "DAT_AI_API_KEY environment variable is required. Get your API key at https://dat.ai/"
    );
  }
  return key;
}

async function datRequest(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = 600000
): Promise<any> {
  const apiKey = getApiKey();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        ...options.headers,
      },
      signal: controller.signal,
    });

    const text = await response.text();
    let data: any;
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }

    if (!response.ok) {
      const errMsg =
        typeof data === "object" && data?.error
          ? typeof data.error === "string"
            ? data.error
            : data.error?.message || JSON.stringify(data.error)
          : `HTTP ${response.status}: ${text}`;
      throw new Error(errMsg);
    }

    return data;
  } finally {
    clearTimeout(timeout);
  }
}

// --- Tool definitions ---

const tools = [
  {
    name: "dat_browse",
    description:
      "Run a browser automation task on dat.ai. Give a natural language instruction and dat.ai will drive a real browser to complete it. Returns the result and any screenshot URLs. Uses sync mode by default (waits for completion, up to 10 min). Set async=true to get a task_id immediately and poll with dat_browse_status.",
    inputSchema: {
      type: "object",
      properties: {
        task: {
          type: "string",
          description:
            "The instruction to execute in the browser, e.g. 'Open https://example.com and summarize the page'",
        },
        async: {
          type: "boolean",
          description: "If true, return a task_id immediately instead of waiting. Poll with dat_browse_status. Default: false",
          default: false,
        },
        screenshots_mode: {
          type: "string",
          enum: ["final_only", "every_step", "on_navigation"],
          description: "Screenshot capture mode. final_only: one screenshot after completion. every_step: screenshot each step. on_navigation: screenshot on URL change. Default: none (no screenshots).",
        },
        full_page: {
          type: "boolean",
          description: "Used by final_only mode. Capture full scrollable page. Default: true.",
          default: true,
        },
        country_iso: {
          type: "string",
          description: "Route to browsing nodes in this country (ISO code, e.g. 'US', 'DE'). Optional.",
        },
        session_key: {
          type: "string",
          description: "Group browsing tasks into a shared session. Optional.",
        },
        timeout: {
          type: "integer",
          description: "Task timeout in milliseconds (max 10800000 = 3 hours). Optional.",
        },
        fanout: {
          type: "integer",
          description: "Number of nodes to race the task on (1-10, default 1). Optional.",
        },
      },
      required: ["task"],
    },
  },
  {
    name: "dat_browse_status",
    description: "Check the status of an async dat.ai browsing task. Returns status (queued/assigned/running/completed/failed) and result if ready.",
    inputSchema: {
      type: "object",
      properties: {
        task_id: {
          type: "string",
          description: "The task_id returned from dat_browse with async=true.",
        },
      },
      required: ["task_id"],
    },
  },
  {
    name: "dat_browse_screenshot",
    description: "Download a screenshot from a completed dat.ai browsing task. Returns the image as base64 data.",
    inputSchema: {
      type: "object",
      properties: {
        task_id: {
          type: "string",
          description: "The browsing task ID.",
        },
        filename: {
          type: "string",
          description: "The screenshot filename, e.g. 'screenshot-01.png'. Get filenames from the browsing result.",
        },
      },
      required: ["task_id", "filename"],
    },
  },
  {
    name: "dat_transcribe",
    description:
      "Transcribe audio to text using dat.ai's Whisper API. Provide audio as a URL (the server will fetch it) or as base64-encoded data. Returns transcribed text. Uses sync mode (waits for completion, up to 10 min).",
    inputSchema: {
      type: "object",
      properties: {
        audio_url: {
          type: "string",
          description: "URL of the audio file to transcribe. The server will download and transcribe it.",
        },
        audio_base64: {
          type: "string",
          description: "Base64-encoded audio data. Will be sent as raw bytes.",
        },
        content_type: {
          type: "string",
          description: "Content-Type of the audio when using audio_base64, e.g. 'audio/wav', 'audio/mpeg', 'audio/mp4'. Default: 'audio/wav'.",
          default: "audio/wav",
        },
        async: {
          type: "boolean",
          description: "If true, return a task_id immediately. Poll with dat_transcribe_status. Default: false.",
          default: false,
        },
      },
    },
  },
  {
    name: "dat_transcribe_status",
    description: "Check the status of an async dat.ai transcription task.",
    inputSchema: {
      type: "object",
      properties: {
        task_id: {
          type: "string",
          description: "The task_id returned from dat_transcribe with async=true.",
        },
      },
      required: ["task_id"],
    },
  },
  {
    name: "dat_completions",
    description:
      "OpenAI-compatible chat completions via dat.ai. Supports streaming and non-streaming. Can enable built-in tools (net, fs, webview) via the datai.tools parameter. Note: tools cannot be used with streaming.",
    inputSchema: {
      type: "object",
      properties: {
        model: {
          type: "string",
          description: "Model name, e.g. 'qwen3:1.7b'",
        },
        messages: {
          type: "array",
          items: {
            type: "object",
            properties: {
              role: { type: "string", enum: ["system", "user", "assistant", "tool"] },
              content: { type: "string" },
            },
            required: ["role", "content"],
          },
          description: "Chat messages array.",
        },
        stream: {
          type: "boolean",
          description: "Enable streaming. Default: false.",
          default: false,
        },
        max_tokens: {
          type: "integer",
          description: "Maximum tokens to generate. Optional.",
        },
        temperature: {
          type: "number",
          description: "Sampling temperature. Optional.",
        },
        top_p: {
          type: "number",
          description: "Nucleus sampling parameter. Optional.",
        },
        stop: {
          type: "string",
          description: "Stop sequence(s). Optional.",
        },
        seed: {
          type: "integer",
          description: "Random seed. Optional.",
        },
        tools: {
          type: "array",
          description: "OpenAI function-calling tools. Optional.",
        },
        tool_choice: {
          type: "string",
          description: "Tool choice strategy. Optional.",
        },
        datai_tools: {
          type: "object",
          properties: {
            net: { type: "boolean", description: "Enable network/HTTP tools." },
            fs: { type: "boolean", description: "Enable filesystem tools." },
            webview: { type: "boolean", description: "Enable browser/webview tools." },
          },
          description: "dat.ai built-in tools. Cannot be used with stream=true.",
        },
      },
      required: ["model", "messages"],
    },
  },
  {
    name: "dat_chat",
    description:
      "Ollama-compatible chat endpoint via dat.ai. Supports NDJSON streaming and non-streaming. Can enable built-in tools (net, fs, webview). Note: tools cannot be used with streaming.",
    inputSchema: {
      type: "object",
      properties: {
        model: {
          type: "string",
          description: "Model name, e.g. 'qwen3:1.7b'",
        },
        messages: {
          type: "array",
          items: {
            type: "object",
            properties: {
              role: { type: "string", enum: ["system", "user", "assistant", "tool"] },
              content: { type: "string" },
            },
            required: ["role", "content"],
          },
          description: "Chat messages array.",
        },
        system: {
          type: "string",
          description: "System prompt. Optional.",
        },
        stream: {
          type: "boolean",
          description: "Enable NDJSON streaming. Default: false.",
          default: false,
        },
        options: {
          type: "object",
          description: "Ollama options (temperature, top_p, top_k, num_predict, num_ctx, stop, seed). Optional.",
        },
        datai_tools: {
          type: "object",
          properties: {
            net: { type: "boolean", description: "Enable network/HTTP tools." },
            fs: { type: "boolean", description: "Enable filesystem tools." },
            webview: { type: "boolean", description: "Enable browser/webview tools." },
          },
          description: "dat.ai built-in tools. Cannot be used with stream=true.",
        },
      },
      required: ["model", "messages"],
    },
  },
];

// --- Tool handlers ---

async function handleDatBrowse(args: any): Promise<any> {
  const { task, async: asyncMode, screenshots_mode, full_page, country_iso, session_key, timeout, fanout } = args;

  const body: any = { task };
  if (screenshots_mode) {
    body.screenshots = { mode: screenshots_mode, full_page: full_page ?? true };
  }
  if (country_iso) {
    body.filter = { country_iso };
  }
  if (session_key) {
    body.session_key = session_key;
  }
  if (timeout) {
    body.timeout = timeout;
  }
  if (fanout) {
    body.fanout = fanout;
  }

  const endpoint = asyncMode ? "/api/v1/browsing/async" : "/api/v1/browsing/sync";
  const result = await datRequest(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result, null, 2),
      },
    ],
  };
}

async function handleDatBrowseStatus(args: any): Promise<any> {
  const { task_id } = args;
  const result = await datRequest(
    `/api/v1/browsing/status?task_id=${encodeURIComponent(task_id)}`,
    { method: "GET" }
  );
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result, null, 2),
      },
    ],
  };
}

async function handleDatBrowseScreenshot(args: any): Promise<any> {
  const { task_id, filename } = args;
  const apiKey = getApiKey();
  const url = `${BASE_URL}/api/v1/browsing/screenshots/${encodeURIComponent(task_id)}/${encodeURIComponent(filename)}`;

  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }

  const buffer = await response.arrayBuffer();
  const base64 = Buffer.from(buffer).toString("base64");
  const contentType = response.headers.get("content-type") || "image/png";

  return {
    content: [
      {
        type: "image",
        data: base64,
        mimeType: contentType,
      },
    ],
  };
}

async function handleDatTranscribe(args: any): Promise<any> {
  const { audio_url, audio_base64, content_type, async: asyncMode } = args;

  const endpoint = asyncMode
    ? "/api/whisper/transcribe/async"
    : "/api/whisper/transcribe/sync";

  let result: any;

  if (audio_url) {
    // Fetch the audio file and send as raw bytes
    const audioResponse = await fetch(audio_url);
    if (!audioResponse.ok) {
      throw new Error(`Failed to fetch audio from URL: HTTP ${audioResponse.status}`);
    }
    const audioBuffer = await audioResponse.arrayBuffer();
    const ct = content_type || audioResponse.headers.get("content-type") || "audio/wav";

    result = await datRequest(endpoint, {
      method: "POST",
      headers: { "Content-Type": ct },
      body: Buffer.from(audioBuffer),
    });
  } else if (audio_base64) {
    const ct = content_type || "audio/wav";
    const buffer = Buffer.from(audio_base64, "base64");
    result = await datRequest(endpoint, {
      method: "POST",
      headers: { "Content-Type": ct },
      body: buffer,
    });
  } else {
    throw new Error("Either audio_url or audio_base64 is required");
  }

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result, null, 2),
      },
    ],
  };
}

async function handleDatTranscribeStatus(args: any): Promise<any> {
  const { task_id } = args;
  const result = await datRequest(
    `/api/whisper/transcribe/status?task_id=${encodeURIComponent(task_id)}`,
    { method: "GET" }
  );
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result, null, 2),
      },
    ],
  };
}

async function handleDatCompletions(args: any): Promise<any> {
  const {
    model,
    messages,
    stream,
    max_tokens,
    temperature,
    top_p,
    stop,
    seed,
    tools,
    tool_choice,
    datai_tools,
  } = args;

  if (stream && datai_tools) {
    throw new Error("Tools cannot be used with streaming (dat.ai returns 400 for this combination).");
  }

  const body: any = { model, messages, stream: stream ?? false };
  if (max_tokens !== undefined) body.max_tokens = max_tokens;
  if (temperature !== undefined) body.temperature = temperature;
  if (top_p !== undefined) body.top_p = top_p;
  if (stop !== undefined) body.stop = stop;
  if (seed !== undefined) body.seed = seed;
  if (tools !== undefined) body.tools = tools;
  if (tool_choice !== undefined) body.tool_choice = tool_choice;
  if (datai_tools) body.datai = { tools: datai_tools };

  if (stream) {
    // For streaming, collect all chunks and return the full text
    const apiKey = getApiKey();
    const response = await fetch(`${BASE_URL}/v1/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    const text = await response.text();
    const lines = text.split("\n").filter((l) => l.startsWith("data: "));
    let fullContent = "";
    for (const line of lines) {
      const json = line.slice(6).trim();
      if (json === "[DONE]") break;
      try {
        const chunk = JSON.parse(json);
        const delta = chunk.choices?.[0]?.delta?.content;
        if (delta) fullContent += delta;
      } catch {}
    }

    return {
      content: [
        {
          type: "text",
          text: fullContent || "(empty response)",
        },
      ],
    };
  }

  const result = await datRequest("/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result, null, 2),
      },
    ],
  };
}

async function handleDatChat(args: any): Promise<any> {
  const { model, messages, system, stream, options, datai_tools } = args;

  if (stream && datai_tools) {
    throw new Error("Tools cannot be used with streaming (dat.ai returns 400 for this combination).");
  }

  const body: any = { model, messages, stream: stream ?? false };
  if (system) body.system = system;
  if (options) body.options = options;
  if (datai_tools) body.datai = { tools: datai_tools };

  if (stream) {
    const apiKey = getApiKey();
    const response = await fetch(`${BASE_URL}/api/chat`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    const text = await response.text();
    const lines = text.split("\n").filter((l) => l.trim());
    let fullContent = "";
    for (const line of lines) {
      try {
        const chunk = JSON.parse(line);
        if (chunk.message?.content) fullContent += chunk.message.content;
        if (chunk.error) throw new Error(chunk.error);
      } catch (e) {
        if (e instanceof Error && !e.message.startsWith("Unexpected")) throw e;
      }
    }

    return {
      content: [
        {
          type: "text",
          text: fullContent || "(empty response)",
        },
      ],
    };
  }

  const result = await datRequest("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(result, null, 2),
      },
    ],
  };
}

// --- Server setup ---

const server = new Server(
  {
    name: "dat-ai-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: t.inputSchema as any,
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "dat_browse":
        return await handleDatBrowse(args);
      case "dat_browse_status":
        return await handleDatBrowseStatus(args);
      case "dat_browse_screenshot":
        return await handleDatBrowseScreenshot(args);
      case "dat_transcribe":
        return await handleDatTranscribe(args);
      case "dat_transcribe_status":
        return await handleDatTranscribeStatus(args);
      case "dat_completions":
        return await handleDatCompletions(args);
      case "dat_chat":
        return await handleDatChat(args);
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error: any) {
    return {
      content: [
        {
          type: "text",
          text: `Error: ${error.message || String(error)}`,
        },
      ],
      isError: true,
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("dat-ai-mcp server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});