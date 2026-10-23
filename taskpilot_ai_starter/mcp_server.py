from datetime import datetime
from mcp.server.fastmcp import FastMCP
from task_store import list_tasks, create_task, complete_task, delete_task, create_meeting, list_meetings

mcp = FastMCP("TaskPilot AI", host="127.0.0.1", port=8001)

@mcp.tool()
def get_pending_tasks() -> dict:
    """Get all tasks that are not completed."""
    result = list_tasks("open")
    return {"ok": result.get("ok", False), "count": result.get("count", 0), "tasks": result.get("tasks", [])}

@mcp.tool()
def add_task(title: str, description: str = "", due_date: str = "", priority: str = "medium") -> dict:
    """Create a task. Priority must be low, medium, or high."""
    return create_task(title, description, due_date, priority)

@mcp.tool()
def mark_task_complete(task_id: int) -> dict:
    """Mark an existing task complete by numeric task ID."""
    return complete_task(task_id)

@mcp.tool()
def remove_task(task_id: int) -> dict:
    """Delete a task by numeric task ID. Use only when requested."""
    return delete_task(task_id)


@mcp.tool()
def add_meeting(
    title: str,
    meeting_date: str = "",
    start_time: str = "",
    end_time: str = "",
    location: str = "",
    notes: str = "",
) -> dict:
    """Add a meeting. ONLY call this tool if the user explicitly provided a specific title (e.g. 'Team Sync', 'Project Review'), date, start time, and end time. Never invent or assume a title if the user didn't give one."""
    from datetime import datetime

    if not title or not title.strip():
        return {"ok": False, "error": "Meeting title is required."}

    # Handle ISO datetime directly if passed in start_time
    if "T" in str(start_time):
        try:
            start_dt = datetime.fromisoformat(str(start_time).strip())
            end_dt = datetime.fromisoformat(str(end_time).strip()) if end_time else None
            if end_dt and end_dt <= start_dt:
                return {"ok": False, "error": "End time must be after start time."}
            return create_meeting(
                title=title.strip(),
                start_time=start_dt.isoformat(),
                end_time=end_dt.isoformat() if end_dt else "",
                location=location,
                notes=notes,
            )
        except ValueError:
            pass

    date_formats = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")
    time_formats = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p")

    parsed_date = None
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(str(meeting_date).strip(), fmt).date()
            break
        except ValueError:
            continue

    if parsed_date is None:
        return {
            "ok": False,
            "error": "Invalid date. Use YYYY-MM-DD, DD-MM-YYYY, or DD/MM/YYYY."
        }

    def parse_time(value):
        for fmt in time_formats:
            try:
                return datetime.strptime(str(value).strip(), fmt).time()
            except ValueError:
                continue
        return None

    start = parse_time(start_time)
    end = parse_time(end_time)

    if start is None or end is None:
        return {
            "ok": False,
            "error": "Invalid time. Use 14:00 or 2:00 PM."
        }

    start_dt = datetime.combine(parsed_date, start)
    end_dt = datetime.combine(parsed_date, end)

    if end_dt <= start_dt:
        return {"ok": False, "error": "End time must be after start time."}

    return create_meeting(
        title=title.strip(),
        start_time=start_dt.isoformat(),
        end_time=end_dt.isoformat(),
        location=location,
        notes=notes,
    )


@mcp.tool()
def get_today_meetings() -> dict:
    """Get meetings scheduled for today's local date."""
    return list_meetings()

@mcp.tool()
def get_meetings_for_date(day: str) -> dict:
    """Get meetings for a specific date in YYYY-MM-DD format."""
    return list_meetings(day)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
