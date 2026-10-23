import json
import os
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv
from openai import OpenAI
from task_store import create_task, list_tasks, complete_task, delete_task, create_meeting, list_meetings

load_dotenv()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
if not OLLAMA_BASE_URL.endswith("/v1"):
    OLLAMA_BASE_URL += "/v1"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
TIMEOUT = float(os.getenv("CLOUD_API_TIMEOUT", "45"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "6"))

TOOLS = [
 {"type":"function","function":{"name":"create_task","description":"Create a persistent task.","parameters":{"type":"object","properties":{"title":{"type":"string"},"description":{"type":"string"},"due_date":{"type":"string"},"priority":{"type":"string","enum":["low","medium","high"]}},"required":["title"],"additionalProperties":False}}},
 {"type":"function","function":{"name":"list_tasks","description":"List tasks. status open, done, or all.","parameters":{"type":"object","properties":{"status":{"type":"string","enum":["all","open","done"]}},"additionalProperties":False}}},
 {"type":"function","function":{"name":"complete_task","description":"Mark task complete by numeric ID.","parameters":{"type":"object","properties":{"task_id":{"type":"integer"}},"required":["task_id"],"additionalProperties":False}}},
 {"type":"function","function":{"name":"delete_task","description":"Delete a task by numeric ID. Only call when user explicitly requests deletion.","parameters":{"type":"object","properties":{"task_id":{"type":"integer"}},"required":["task_id"],"additionalProperties":False}}},
 {"type":"function","function":{"name":"create_meeting","description":"Create a meeting. start_time and end_time must be ISO local datetime strings, e.g. 2026-10-25T14:00.","parameters":{"type":"object","properties":{"title":{"type":"string"},"start_time":{"type":"string"},"end_time":{"type":"string"},"location":{"type":"string"},"notes":{"type":"string"}},"required":["title","start_time","end_time"],"additionalProperties":False}}},
 {"type":"function","function":{"name":"list_meetings","description":"List meetings on a date YYYY-MM-DD. Omit day for today.","parameters":{"type":"object","properties":{"day":{"type":"string"}},"additionalProperties":False}}}]

def _run_tool(name, a):
    if name == "create_task":
        return create_task(a.get("title",""), a.get("description",""), a.get("due_date",""), a.get("priority","medium"))
    if name == "list_tasks": return list_tasks(a.get("status","all"))
    if name == "complete_task": return complete_task(int(a["task_id"]))
    if name == "delete_task": return delete_task(int(a["task_id"]))
    if name == "create_meeting": return create_meeting(a.get("title",""),a.get("start_time",""),a.get("end_time",""),a.get("location",""),a.get("notes",""))
    if name == "list_meetings": return list_meetings(a.get("day",""))
    return {"ok":False,"error":"Unknown tool"}

def _local_ai(message):
    client=OpenAI(base_url=OLLAMA_BASE_URL,api_key="ollama",timeout=TIMEOUT)
    messages=[
      {"role":"system","content":"You are TaskPilot AI, a concise employee productivity assistant. Use tools for all task/meeting facts and changes. Never invent tool results. For meetings, collect missing date, start time, end time, and title before calling the tool. Use ISO local date/time. For email requests, write a draft and clearly say it has not been sent. For summaries, query task and meeting tools."},
      {"role":"user","content":message}
    ]
    for _ in range(MAX_AGENT_STEPS):
        response=client.chat.completions.create(model=OLLAMA_MODEL,messages=messages,tools=TOOLS,tool_choice="auto",temperature=0.2)
        m=response.choices[0].message
        messages.append(m.model_dump(exclude_none=True))
        if not m.tool_calls: return m.content or "I couldn't generate a response."
        for call in m.tool_calls:
            try:
                args=json.loads(call.function.arguments or "{}")
                result=_run_tool(call.function.name,args)
            except Exception as exc: result={"ok":False,"error":str(exc)}
            messages.append({"role":"tool","tool_call_id":call.id,"content":json.dumps(result,ensure_ascii=False,default=str)})
    return "I reached the action limit. Please try a simpler request."

def _fallback(message):
    """Reliable basic commands if Ollama is not running; no fabricated AI response."""
    text=message.strip()
    low=text.lower()
    if any(k in low for k in ("draft an email","write an email","help me write an email","email draft")):
        subject="Project update"
        m=re.search(r"subject\s*:\s*(.+)",text,re.I)
        if m: subject=m.group(1).strip()
        return "Email draft (not sent):\nSubject: "+subject+"\n\nHi,\n\nI wanted to share a quick update on the project. Please let me know if you have any questions or would like to discuss the next steps.\n\nBest regards"
    if any(k in low for k in ("today's meeting","meetings today","what meetings","show meetings","my schedule")):
        r=list_meetings()
        if not r.get("meetings"): return "You have no meetings saved for today."
        return "Today's meetings:\n"+"\n".join(f"- {x['start_time'][11:16]}–{x['end_time'][11:16] if x['end_time'] else '—'} {x['title']}" for x in r["meetings"])
    if "meeting" in low and any(k in low for k in ("schedule","add","create","book")):
        return "I can save meetings, but please use the meeting form or provide details in this format: 'Schedule meeting: Team sync; date 2026-10-25; start 14:00; end 14:30; location Office'. Ollama is currently unavailable, so natural-language extraction is disabled."
    if any(k in low for k in ("show my tasks","list tasks","show all tasks","pending tasks","open tasks","my tasks")):
        status="open" if any(k in low for k in ("pending","open")) else "all"
        r=list_tasks(status)
        if not r["tasks"]: return "You have no "+("open " if status=="open" else "")+"tasks saved."
        return "Your tasks:\n"+"\n".join(f"#{t['id']} {t['title']} — {t['status']} ({t['priority']} priority)" for t in r["tasks"])
    m=re.search(r"(?:complete|finish|mark)\s+(?:task\s*)?#?(\d+)",low)
    if m:
        r=complete_task(int(m.group(1)))
        return f"Marked task #{m.group(1)} complete." if r.get("ok") else r.get("error","Could not complete task.")
    m=re.search(r"(?:delete|remove)\s+(?:task\s*)?#?(\d+)",low)
    if m:
        r=delete_task(int(m.group(1)))
        return f"Deleted task: {r.get('title','')}." if r.get("ok") else r.get("error","Could not delete task.")
    m=re.search(r"(?:create|add)\s+(?:a\s+)?(?:high[- ]priority\s+)?task\s+(?:to\s+)?(.+)",text,re.I)
    if m:
        title=re.sub(r"\s+(?:tomorrow|today)\.?$","",m.group(1),flags=re.I).strip(" .")
        priority="high" if "high-priority" in low or "high priority" in low else "medium"
        due=(datetime.now().astimezone().date()+timedelta(days=1)).isoformat() if "tomorrow" in low else (datetime.now().astimezone().date().isoformat() if "today" in low else "")
        r=create_task(title,due_date=due,priority=priority)
        return f"Created task #{r['task']['id']}: {r['task']['title']}." if r.get("ok") else r.get("error","Could not create task.")
    return ("Ollama is not reachable, so I couldn't process this as a free-form AI request. "
            "Start Ollama and ensure model '"+OLLAMA_MODEL+"' is installed. Basic task commands remain available.")

def chat(message: str) -> str:
    provider=os.getenv("AI_PROVIDER","local").strip().lower()
    if provider in ("local","auto"):
        try: return _local_ai(message)
        except Exception as exc:
            print(f"Local Ollama unavailable: {type(exc).__name__}: {exc}")
            return _fallback(message)
    return "Cloud AI is disabled for this local-first build. Set AI_PROVIDER=local and start Ollama."
