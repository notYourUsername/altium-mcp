"""
MCP write-action activity log (audit trail).

Records every board/design/library-modifying tool call so there is a human-readable
trail of what the assistant changed. Read-only queries log nothing.

Design note (fail-safe classification): instead of an allowlist of write commands
(which silently misses any new write tool that isn't added to it), we treat a command
as a WRITE unless it is an obvious read -- it starts with `get_`/`search_`, or is in a
small explicit read-only denylist. This way new write tools are logged by default and
cannot silently miss the audit log.

Pure Python (no Altium/Windows deps) so it is unit-tested offline; main.py calls
append_activity() from execute_command.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

# Serializes appends so concurrent writes never interleave/lose a line.
_LOCK = threading.Lock()

# Read-only commands that do NOT start with get_/search_ (so they would otherwise be
# mis-classified as writes). Keep this list small and explicit.
READ_ONLY_COMMANDS = {
    "take_view_screenshot",
    "fab_measure",  # DFM measurement for check_against_fab; reads only
}


def is_write_command(command: str) -> bool:
    """Fail-safe: anything that is not an obvious read is treated as a write.

    Reads = commands starting with `get_` or `search_`, plus READ_ONLY_COMMANDS.
    Everything else (create_*, update_*, set_*, move_*, run_*, layout_duplicator_apply,
    and any future write tool) is logged.
    """
    if not command:
        return False
    if command in READ_ONLY_COMMANDS:
        return False
    if command.startswith("get_") or command.startswith("search_"):
        return False
    return True


def _operation_succeeded(response: Any) -> bool:
    """Did the *operation* succeed?

    The bridge wraps every script result as {"success": <script ran>, "result": <output>}.
    Top-level success only means the script executed; the operation's own success/error
    lives in result. So a soft failure (e.g. "Rule not found") arrives as
    {"success": true, "result": {"success": false, "error": "..."}}. Report ERR for those.
    """
    if not isinstance(response, dict):
        return False
    if not response.get("success", False):
        return False
    result = response.get("result")
    if isinstance(result, dict) and "success" in result:
        return bool(result.get("success", False))
    return True


def _summary(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    if response.get("error"):
        return str(response["error"])
    result = response.get("result", response)
    if isinstance(result, dict):
        return str(result.get("message") or result.get("error") or "")
    return ""


def format_activity_line(
    command: str,
    params: Optional[Dict[str, Any]],
    response: Any,
    now: Optional[str] = None,
) -> Optional[str]:
    """Return a one-line audit entry for a WRITE command, or None to skip it."""
    if not is_write_command(command):
        return None
    ts = now or time.strftime("%Y-%m-%d %H:%M:%S")
    status = "OK " if _operation_succeeded(response) else "ERR"
    try:
        pstr = json.dumps(params or {}, ensure_ascii=False, sort_keys=True)
    except Exception:
        pstr = str(params)
    line = f"[{ts}] {status} {command} params={pstr}"
    summary = _summary(response)
    if summary:
        line += f" - {summary}"
    return line


def append_activity(log_path, command: str, params, response) -> bool:
    """Append an audit line for write commands. Returns True if a line was written.

    Opens the file in append mode under a lock so concurrent writes are atomic.
    """
    line = format_activity_line(command, params, response)
    if line is None:
        return False
    with _LOCK:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return True
