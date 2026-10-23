import asyncio
from datetime import datetime, timedelta
import json
import os
import re

from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from task_store import list_tasks, create_task, complete_task, delete_task, list_meetings

load_dotenv()

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", "http://localhost:11434"
).rstrip("/")

if not OLLAMA_BASE_URL.endswith("/v1"):
    OLLAMA_BASE_URL += "/v1"

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL", "http://127.0.0.1:8001/mcp"
)
TIMEOUT = float(os.getenv("CLOUD_API_TIMEOUT", "45"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "6"))


def _json_safe(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def _fallback(message: str) -> str:
    """Reliable basic fallback commands if Ollama/MCP is unreachable."""
    text = message.strip()
    low = text.lower()
    if any(k in low for k in ("draft an email", "write an email", "help me write an email", "email draft")):
        subject = "Project update"
        m = re.search(r"subject\s*:\s*(.+)", text, re.I)
        if m:
            subject = m.group(1).strip()
        return (
            "Email draft (not sent):\n"
            f"Subject: {subject}\n\n"
            "Hi,\n\n"
            "I wanted to share a quick update on the project. "
            "Please let me know if you have any questions or would like to discuss the next steps.\n\n"
            "Best regards"
        )
    if any(k in low for k in ("today's meeting", "meetings today", "what meetings", "show meetings", "my schedule")):
        r = list_meetings()
        if not r.get("meetings"):
            return "You have no meetings saved for today."
        return "Today's meetings:\n" + "\n".join(
            f"- {x['start_time'][11:16]}–{x['end_time'][11:16] if x['end_time'] else '—'} {x['title']}"
            for x in r["meetings"]
        )
    if "meeting" in low and any(k in low for k in ("schedule", "add", "create", "book")):
        return (
            "I can save meetings, but please use the meeting form or provide details in this format: "
            "'Schedule meeting: Team sync; date 2026-10-25; start 14:00; end 14:30; location Office'. "
            "Ollama is currently unavailable, so natural-language extraction is disabled."
        )
    if any(k in low for k in ("show my tasks", "list tasks", "show all tasks", "pending tasks", "open tasks", "my tasks")):
        status = "open" if any(k in low for k in ("pending", "open")) else "all"
        r = list_tasks(status)
        if not r.get("tasks"):
            return "You have no " + ("open " if status == "open" else "") + "tasks saved."
        return "Your tasks:\n" + "\n".join(
            f"#{t['id']} {t['title']} — {t['status']} ({t['priority']} priority)"
            for t in r["tasks"]
        )
    m = re.search(r"(?:complete|finish|mark)\s+(?:task\s*)?#?(\d+)", low)
    if m:
        r = complete_task(int(m.group(1)))
        return f"Marked task #{m.group(1)} complete." if r.get("ok") else r.get("error", "Could not complete task.")
    m = re.search(r"(?:delete|remove)\s+(?:task\s*)?#?(\d+)", low)
    if m:
        r = delete_task(int(m.group(1)))
        return f"Deleted task: {r.get('title', '')}." if r.get("ok") else r.get("error", "Could not delete task.")
    m = re.search(r"(?:create|add)\s+(?:a\s+)?(?:high[- ]priority\s+)?task\s+(?:to\s+)?(.+)", text, re.I)
    if m:
        title = re.sub(r"\s+(?:tomorrow|today)\.?$", "", m.group(1), flags=re.I).strip(" .")
        priority = "high" if "high-priority" in low or "high priority" in low else "medium"
        due = (
            (datetime.now().astimezone().date() + timedelta(days=1)).isoformat()
            if "tomorrow" in low
            else (datetime.now().astimezone().date().isoformat() if "today" in low else "")
        )
        r = create_task(title, due_date=due, priority=priority)
        return f"Created task #{r['task']['id']}: {r['task']['title']}." if r.get("ok") else r.get("error", "Could not create task.")

    return (
        "I couldn't connect to the local AI or MCP tools. "
        "Check that Ollama and the MCP server are running, then try again."
    )


def _has_explicit_meeting_title(msg: str) -> bool:
    cleaned = re.sub(
        r"(?i)\b(please|can you|could you|schedule|create|add|book|set up|new|a|an|the|meeting|tomorrow|today|yesterday|from|to|at|on|for|pm|am|hours?|mins?|minutes?|\d{1,2}(?::\d{2})?)\b",
        " ",
        msg,
    )
    cleaned = re.sub(r"[^a-zA-Z0-9]", "", cleaned)
    return len(cleaned) > 2


async def _local_ai_async(message: str) -> str:
    async with AsyncOpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        timeout=TIMEOUT,
    ) as client:
        async with streamable_http_client(MCP_SERVER_URL) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                available = await session.list_tools()

                tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or tool.name,
                            "parameters": tool.inputSchema,
                        },
                    }
                    for tool in available.tools
                ]

                now_dt = datetime.now().astimezone()
                today_str = now_dt.strftime("%Y-%m-%d (%A)")
                tomorrow_str = (now_dt.date() + timedelta(days=1)).isoformat()

                system_prompt = (
                    "You are TaskPilot AI, a concise and reliable productivity assistant. "
                    f"Today's date is {today_str}. Tomorrow's date is {tomorrow_str}. "
                    "When the user mentions dates like 'today', 'tomorrow', or weekdays, calculate the exact date based on today's date. "
                    "Use MCP tools to retrieve task and meeting facts and to perform requested changes. "
                    "Never invent tool results or claim an action succeeded unless confirmed by the tool result. "
                    "CRITICAL RULE FOR MEETINGS: Before calling 'add_meeting', verify that the user provided ALL required information: 1) a specific meeting title/topic, 2) date, 3) start time, and 4) end time. If the user asks to schedule or create a meeting but did NOT provide a specific title (or omits time/date), DO NOT call 'add_meeting' and NEVER invent or guess a title (such as 'Meeting with John' or 'Discussion'). Instead, immediately ask the user to provide the missing information. "
                    "Use YYYY-MM-DD dates and 24-hour times (e.g., 14:00) when calling tools. "
                    "Do not delete anything unless the user explicitly asks. "
                    "For email requests, write a professional draft and clearly state that it is a draft only and has not been sent. "
                    "For daily planning or summaries, query the task and meeting tools first."
                )

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]

                for _ in range(MAX_AGENT_STEPS):
                    response = await client.chat.completions.create(
                        model=OLLAMA_MODEL,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.2,
                    )

                    assistant_message = response.choices[0].message
                    messages.append(
                        assistant_message.model_dump(exclude_none=True)
                    )

                    if not assistant_message.tool_calls:
                        if assistant_message.content and assistant_message.content.strip():
                            return assistant_message.content
                        fallback_res = _fallback(message)
                        if fallback_res and "I couldn't connect to the local AI" not in fallback_res:
                            return fallback_res
                        return "I couldn't generate a response."

                    for call in assistant_message.tool_calls:
                        try:
                            arguments = json.loads(
                                call.function.arguments or "{}"
                            )

                            if call.function.name == "add_meeting" and not _has_explicit_meeting_title(message):
                                tool_output = _json_safe(
                                    {
                                        "ok": False,
                                        "error": (
                                            "Meeting title is required. The user did not specify what the meeting is called. "
                                            "Ask the user for the title or subject of the meeting before creating it."
                                        ),
                                    }
                                )
                            else:
                                result = await session.call_tool(
                                    call.function.name,
                                    arguments,
                                )

                                content = []
                                for item in result.content:
                                    if hasattr(item, "text"):
                                        content.append(item.text)

                                tool_output = "\n".join(content) or _json_safe(
                                    {"ok": not result.isError}
                                )

                                if result.isError:
                                    tool_output = _json_safe(
                                        {"ok": False, "error": tool_output}
                                    )

                        except Exception as exc:
                            tool_output = _json_safe(
                                {
                                    "ok": False,
                                    "error": f"{type(exc).__name__}: {exc}",
                                }
                            )

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": tool_output,
                            }
                        )

                return "I reached the action limit. Please try a simpler request."


def chat(message: str) -> str:
    provider = os.getenv("AI_PROVIDER", "local").strip().lower()

    if provider not in ("local", "auto"):
        return (
            "Cloud AI is disabled. Set AI_PROVIDER=local "
            "and start Ollama."
        )

    try:
        return asyncio.run(_local_ai_async(message))
    except Exception as exc:
        print(
            f"TaskPilot AI error: {type(exc).__name__}: {exc}"
        )
        return _fallback(message)
