<div align="center">

<img src="assets/dat-logo-white.png" width="180" alt="dat.ai" />

# dat.ai MCP Server

*Browser automation, transcription, and LLM chat as MCP tools for any agent.*

![license](https://img.shields.io/badge/license-MIT-blue)
![pypi](https://img.shields.io/badge/pypi-dat--ai--mcp-red)
![tools](https://img.shields.io/badge/tools-7-green)
![python](https://img.shields.io/badge/python-3.10+-blue)

</div>

---

## Tools

| Tool | Endpoint | Description |
|------|----------|-------------|
| `dat_browse` | `POST /api/v1/browsing/{async,sync}` | Natural language browser automation. Sync (waits up to 10 min) or async (returns task_id immediately). Optional screenshots |
| `dat_browse_status` | `GET /api/v1/browsing/status` | Poll an async browsing task. Returns status + result if ready |
| `dat_browse_screenshot` | `GET /api/v1/browsing/screenshots/{task_id}/{file}` | Download a screenshot as base64 image data |
| `dat_transcribe` | `POST /api/whisper/transcribe/{async,sync}` | Whisper speech-to-text. Accepts audio URL or base64. Sync or async |
| `dat_transcribe_status` | `GET /api/whisper/transcribe/status` | Poll an async transcription task |
| `dat_completions` | `POST /v1/chat/completions` | OpenAI-compatible chat completions. Streaming, function calling, built-in dat.ai tools (net/fs/webview) |
| `dat_chat` | `POST /api/chat` | Ollama-compatible chat. NDJSON streaming, system prompts, built-in tools |

## Setup

### Get an API key

Sign up at [dat.ai](https://dat.ai) and get your API key from the dashboard. See the [official API docs](https://dat-48188875.mintlify.app/pages/introduction) for reference.

### Hermes Agent (one-line install)

```bash
hermes plugins install willtholke/dat.ai-mcp --enable
```

Restart Hermes after installing. Set your API key in `~/.hermes/.env`:

```
DAT_AI_API_KEY=your-api-key-here
```

The plugin registers all 7 tools as native Hermes tools. No MCP config needed.

### Other MCP clients

Install the package:

```bash
pip install dat-ai-mcp
```

Or use directly with `uvx` (no install needed):

```bash
uvx dat-ai-mcp
```

Set the `DAT_AI_API_KEY` environment variable and add the server to your MCP client config

#### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dat-ai": {
      "command": "uvx",
      "args": ["dat-ai-mcp"],
      "env": {
        "DAT_AI_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

#### Cursor / other MCP clients

Same pattern: command `uvx`, args `["dat-ai-mcp"]`, env `DAT_AI_API_KEY`

### Environment variable

```
DAT_AI_API_KEY=your-api-key-here
```

## Usage examples

### Browser automation

```
dat_browse({
  task: "Open https://example.com and summarize the page",
  screenshots_mode: "final_only"
})
```

### Audio transcription

```
dat_transcribe({
  audio_url: "https://example.com/audio.mp3"
})
```

### Chat completions with built-in tools

```
dat_completions({
  model: "qwen3:1.7b",
  messages: [{ role: "user", content: "Open https://example.com and summarize the page" }],
  datai_tools: { net: true, webview: true }
})
```

## Development

```bash
git clone https://github.com/willtholke/dat.ai-mcp.git
cd dat.ai-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## License

[MIT](LICENSE)

## Note

Special thanks to dat.ai co-founder & COO Eugenia Dushina for setting me up with the platform

---