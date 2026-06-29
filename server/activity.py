"""
MCP write-action activity log (audit trail).

Records only board/design-modifying tool calls so there is a human-readable trail
of what the assistant changed. Pure Python (no Altium/Windows deps) so it is
unit-testable offline; main.py calls append_activity() from execute_command.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

# Commands that modify the board/design/library (worth auditing). Read-only
# queries (get_*) are intentionally excluded.
WRITE_COMMANDS = {
    "create_net_class",
    "create_clearance_rule",
    "run_drc",                 # repours polygons + (re)creates violation markers
    "move_components",
    "set_component_position",
    "create_pcb_footprint",
    "create_schematic_symbol",
    "layout_duplicator_apply",
}


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
    if command not in WRITE_COMMANDS:
        return None
    ts = now or time.strftime("%Y-%m-%d %H:%M:%S")
    ok = isinstance(response, dict) and bool(response.get("success", False))
    status = "OK " if ok else "ERR"
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
    """Append an audit line for write commands. Returns True if a line was written."""
    line = format_activity_line(command, params, response)
    if line is None:
        return False
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return True
