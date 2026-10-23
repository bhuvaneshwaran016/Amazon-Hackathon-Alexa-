# TaskPilot AI — Local Hackathon Demo

TaskPilot AI is a local-first employee productivity assistant built with FastAPI, SQLite, Ollama, and an MCP server. It supports tasks, meeting scheduling, local AI tool calling, and email drafting (draft only; no email is sent).

## Requirements
- Windows 10/11
- Python 3.11+ (Python 3.12 is supported)
- Ollama installed for free local AI responses (optional for basic task commands)
- A model available in Ollama, for example `qwen2.5:3b`

## Setup (PowerShell)
Open PowerShell in the project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If activation is blocked:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install/start Ollama and download a model once:
```powershell
ollama pull qwen2.5:3b
ollama serve
```
If Ollama already runs as a Windows service, do not start a second `ollama serve` process.

## Run the web app
Terminal 1:
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app:app --reload --port 8000
```
Open http://127.0.0.1:8000

## Run MCP server
Terminal 2, in the same project folder:
```powershell
.\.venv\Scripts\Activate.ps1
python mcp_server.py
```
MCP endpoint: http://127.0.0.1:8001/mcp

## What works
- Persistent SQLite task creation, listing, completion, deletion
- Meeting creation with date, start time, end time, location, notes
- Today's meetings list
- Natural-language agent using Ollama's OpenAI-compatible local API and tool calls
- Basic task commands and email draft fallback when Ollama is not running
- MCP tools for tasks and meetings
- Frontend forms and task-board actions

If Ollama is unavailable, the app can still handle a subset of simple task commands. Full free-form natural-language understanding requires the local model to be running.

## Try these demo prompts
- `Create a high-priority task to finish my hackathon submission tomorrow`
- `Show my open tasks`
- `Mark task 1 complete`
- `Schedule a team meeting tomorrow at 2 PM` (with Ollama running; if not, use the meeting form)
- `Draft an email about the project update`
- `Plan my day using my tasks and meetings`

## Troubleshooting
- Check `http://127.0.0.1:8000/api/health`.
- Check Ollama with `ollama list` and `ollama run qwen2.5:3b`.
- Ensure `OLLAMA_BASE_URL=http://localhost:11434` (the app adds `/v1` automatically).
- Keep `.env` private. Do not expose the local MCP endpoint publicly without HTTPS and authentication.

## Scope and honest limitations
This is a working local prototype, not an officially integrated Alexa+ product. It does not send email or connect to a live Outlook/Google calendar. Alexa+ connectivity, voice interaction, and remote deployment require separate supported integrations and testing.
