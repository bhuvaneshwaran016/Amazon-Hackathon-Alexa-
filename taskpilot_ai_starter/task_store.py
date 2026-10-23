import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.getenv("TASKPILOT_DB", str(Path(__file__).with_name("taskpilot.db")))

def connect():
    path = Path(DB_PATH)
    if str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=10)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            due_date TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )""")

def create_task(title: str, description: str = "", due_date: str = "", priority: str = "medium"):
    title = (title or "").strip()
    if not title:
        return {"ok": False, "error": "Task title cannot be empty."}
    if len(title) > 180:
        return {"ok": False, "error": "Task title must be 180 characters or fewer."}
    priority = (priority or "medium").lower().strip()
    if priority not in {"low", "medium", "high"}:
        priority = "medium"
    init_db()
    with connect() as con:
        cur = con.execute(
            "INSERT INTO tasks(title,description,due_date,priority,status,created_at) VALUES(?,?,?,?,?,?)",
            (title, (description or "")[:2000], (due_date or "")[:40], priority, "open",
             datetime.now(timezone.utc).isoformat())
        )
        return {"ok": True, "task": dict(con.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone())}

def list_tasks(status: str = "all"):
    status = (status or "all").lower()
    if status not in {"all", "open", "done"}: status = "all"
    init_db()
    with connect() as con:
        if status == "all":
            rows = con.execute("SELECT * FROM tasks ORDER BY (status='done') ASC, id DESC").fetchall()
        else:
            rows = con.execute("SELECT * FROM tasks WHERE status=? ORDER BY id DESC", (status,)).fetchall()
        return {"ok": True, "tasks": [dict(r) for r in rows], "count": len(rows)}

def complete_task(task_id: int):
    init_db()
    with connect() as con:
        cur = con.execute("UPDATE tasks SET status='done' WHERE id=?", (int(task_id),))
        if cur.rowcount == 0: return {"ok": False, "error": f"No task found with id {task_id}."}
        return {"ok": True, "task": dict(con.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone())}

def delete_task(task_id: int):
    init_db()
    with connect() as con:
        row = con.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone()
        if row is None: return {"ok": False, "error": f"No task found with id {task_id}."}
        con.execute("DELETE FROM tasks WHERE id=?", (int(task_id),))
        return {"ok": True, "deleted_id": int(task_id), "title": row["title"]}

def create_meeting(title: str, start_time: str, end_time: str = "", location: str = "", notes: str = ""):
    title = (title or "").strip()
    if not title: return {"ok": False, "error": "Meeting title is required."}
    try:
        start_dt = datetime.fromisoformat((start_time or "").strip())
        end_dt = datetime.fromisoformat((end_time or "").strip()) if end_time else None
    except ValueError:
        return {"ok": False, "error": "Use a valid date/time, such as 2026-10-25T14:00:00."}
    if end_dt and end_dt <= start_dt:
        return {"ok": False, "error": "Meeting end time must be after its start time."}
    init_db()
    with connect() as con:
        cur = con.execute("""INSERT INTO meetings(title,start_time,end_time,location,notes,created_at)
            VALUES(?,?,?,?,?,?)""", (title[:180], start_dt.isoformat(timespec="minutes"),
            end_dt.isoformat(timespec="minutes") if end_dt else "", (location or "")[:300],
            (notes or "")[:2000], datetime.now(timezone.utc).isoformat()))
        return {"ok": True, "meeting": dict(con.execute("SELECT * FROM meetings WHERE id=?", (cur.lastrowid,)).fetchone())}

def list_meetings(day: str = ""):
    if not day: day = datetime.now().astimezone().date().isoformat()
    try: datetime.strptime(day, "%Y-%m-%d")
    except ValueError: return {"ok": False, "error": "Date must use YYYY-MM-DD format."}
    init_db()
    with connect() as con:
        rows = con.execute("SELECT * FROM meetings WHERE substr(start_time,1,10)=? ORDER BY start_time ASC", (day,)).fetchall()
        return {"ok": True, "date": day, "meetings": [dict(r) for r in rows], "count": len(rows)}
