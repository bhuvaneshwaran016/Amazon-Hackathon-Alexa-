
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import chat
from task_store import (
    create_task,
    list_tasks,
    complete_task,
    delete_task,
    create_meeting,
    list_meetings,
)

app = FastAPI(title="TaskPilot AI", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Request models

class TaskRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    due_date: str = ""
    priority: str = "medium"


class MeetingRequest(BaseModel):
    title: str = Field(..., min_length=1)
    meeting_date: str = ""
    start_time: str
    end_time: str
    location: str = ""
    notes: str = ""


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ConnectAccountRequest(BaseModel):
    email: str = Field(..., min_length=3)


# Web page

@app.get("/")
def home():
    if not INDEX_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="static/index.html was not found.",
        )
    return FileResponse(str(INDEX_FILE))


# Health check

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "app": "TaskPilot AI",
        "ai_provider": "local",
        "timestamp": datetime.now().astimezone().isoformat(),
    }


# Tasks

@app.get("/api/tasks")
def get_tasks(status: str = "all"):
    result = list_tasks(status)
    if not result.get("ok", False):
        raise HTTPException(status_code=500, detail="Could not retrieve tasks.")
    return result


@app.post("/api/tasks")
def add_task(body: TaskRequest):
    result = create_task(
        title=body.title.strip(),
        description=body.description,
        due_date=body.due_date,
        priority=body.priority,
    )
    if not result.get("ok", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Could not create task."))
    return result


@app.post("/api/tasks/{task_id}/complete")
def mark_task_complete(task_id: int):
    result = complete_task(task_id)
    if not result.get("ok", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Could not complete task."))
    return result


@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: int):
    result = delete_task(task_id)
    if not result.get("ok", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Could not delete task."))
    return result


# Meetings

@app.get("/api/meetings")
def get_meetings(day: str = ""):
    result = list_meetings(day)
    if not result.get("ok", False):
        raise HTTPException(status_code=500, detail="Could not retrieve meetings.")
    return result


@app.post("/api/meetings")
def add_meeting(body: MeetingRequest):
    start_time = body.start_time.strip()
    end_time = body.end_time.strip()
    meeting_date = body.meeting_date.strip()

    if meeting_date:
        if "T" not in start_time:
            start_time = f"{meeting_date}T{start_time}"
        if end_time and "T" not in end_time:
            end_time = f"{meeting_date}T{end_time}"

    result = create_meeting(
        title=body.title.strip(),
        start_time=start_time,
        end_time=end_time,
        location=body.location,
        notes=body.notes,
    )
    if not result.get("ok", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Could not create meeting."))
    return result


# AI chat

@app.post("/api/chat")
def chat_endpoint(body: ChatRequest):
    try:
        reply = chat(body.message.strip())

        tasks_result = list_tasks("all")
        meetings_result = list_meetings()

        return {
            "reply": reply,
            "tasks": tasks_result.get("tasks", []),
            "meetings": meetings_result.get("meetings", []),
        }
    except Exception as exc:
        print(f"Chat error: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="TaskPilot could not process this request. Check the server terminal.",
        )


# Connect Account (Calendar & Work Details Sync)

@app.post("/api/connect-account")
def connect_account(body: ConnectAccountRequest):
    email = body.email.strip()
    username = email.split("@")[0].replace(".", " ").title() if "@" in email else email.title()
    today = datetime.now().astimezone().date()
    today_str = today.isoformat()
    tomorrow_str = (today + timedelta(days=1)).isoformat()

    sample_meetings = [
        {
            "title": f"Sprint Standup · {username}",
            "start_time": f"{today_str}T10:00",
            "end_time": f"{today_str}T10:30",
            "location": "Virtual / Chime",
            "notes": f"Daily sync with engineering team for {email}.",
        },
        {
            "title": "Architecture Review & Demo Prep",
            "start_time": f"{today_str}T14:30",
            "end_time": f"{today_str}T15:30",
            "location": "Conference Room A",
            "notes": "Discuss Hackathon MVP architecture and local Ollama privacy benchmarks.",
        },
        {
            "title": "1:1 with Team Lead",
            "start_time": f"{tomorrow_str}T11:00",
            "end_time": f"{tomorrow_str}T11:45",
            "location": "Meeting Room 3",
            "notes": "Weekly work progress and roadmap deliverables review.",
        },
    ]

    sample_tasks = [
        {
            "title": "Review Pull Request #142 (Model Integration)",
            "description": f"Assigned to {email} from work queue.",
            "due_date": today_str,
            "priority": "high",
        },
        {
            "title": "Finalize Hackathon Presentation Deck",
            "description": "Include benchmarks on local AI privacy & MCP latency.",
            "due_date": tomorrow_str,
            "priority": "high",
        },
        {
            "title": "Update project documentation & README",
            "description": "Document MCP tools and startup commands.",
            "due_date": tomorrow_str,
            "priority": "medium",
        },
    ]

    created_m = 0
    for m in sample_meetings:
        res = create_meeting(
            title=m["title"],
            start_time=m["start_time"],
            end_time=m["end_time"],
            location=m["location"],
            notes=m["notes"],
        )
        if res.get("ok"):
            created_m += 1

    created_t = 0
    for t in sample_tasks:
        res = create_task(
            title=t["title"],
            description=t["description"],
            due_date=t["due_date"],
            priority=t["priority"],
        )
        if res.get("ok"):
            created_t += 1

    return {
        "ok": True,
        "email": email,
        "name": username,
        "synced_meetings": created_m,
        "synced_tasks": created_t,
        "message": f"Connected {email}! Synced {created_m} calendar meetings and {created_t} work tasks.",
    }
