# Altium MCP — new tools catalog (server build 2026-06-30-b8)

Tools added in this development cycle, grouped by area. All coordinates/sizes are in
**mils, relative to board origin** unless noted. Run `get_server_version` to confirm a
chat is on this build; run `run_self_test` after any restart to confirm health.

## Reliability / QA
- **get_server_version** — reports the running build string. If it's older than expected, the chat is on a stale server process (restart + new chat).
- **run_self_test** — exercises all read-only bridge commands, reports pass/fail in one call.
- **design_review** — one-call board snapshot: board info, DRC-by-type, unrouted signal count, rule count.

## Analysis / reporting
- **get_drc_summary(fresh=False)** — DRC violations grouped by type (vs the raw 100-line list).
- **get_net_classes** — lists object classes (net classes = kind "Net"); confirms `InNetClass(...)` names.
- **get_routing_status** — ratsnest-based routed/unrouted split (no plane miscount) + routed lengths.
- **get_unrouted_nets** — now flags `has_pour` per net and reports `total_unrouted_signal_nets`.
- **get_diff_pair_skew(tolerance_mils=5)** — intra-pair length skew for diff pairs (from net naming), flags pairs over tolerance.

## Rules
- **clone_rule(source, new_name, scope1, scope2, enabled)** — copy a fully-configured rule (gap/impedance/tolerance and all) and re-scope it. The way to set high-speed constraints that aren't directly script-settable. Templates on board: `TPL_DIFF_USB2_90R`, `TPL_DIFF_CAN_120R`, `TPL_Z_USB2_90R`, `TPL_Z_CAN_120R`, `TPL_MATCH_10MIL` (recreate with clone if missing).
- **create_diff_pair_rule / create_impedance_rule / create_length_match_rule** — create correctly-typed, scoped rules (diff-pair also sets per-layer min/max width); specialized constraint left at default with a `constraint_note` (use clone_rule for exact values).

## Placement
- **align_components(designators, axis, mode)** — snap to a common X or Y line.
- **distribute_components(designators, axis, spacing)** — even spacing along an axis.
- **place_relative(cmp, anchor, dx, dy, anchor_pad, rotation)** — place a part at an offset from another part's pad (e.g. a decoupling cap by an IC pin).
- **auto_place_decoupling(ic, offset_mils)** — rough-place each decoupling cap beside its IC power pin.

## Vias / routing
- **add_via(x, y, net, pad_mils, hole_mils)** — through via, optional net; returns `net_found`.
- **add_track(x1,y1,x2,y2, layer, width_mils, net)** — straight copper segment (point-to-point assist, not autoroute).
- **delete_via_near(x, y, tol_mils)** — remove the nearest free via.
- **stitch_vias(x1,y1,x2,y2, pitch_mils, net, pad_mils, hole_mils)** — row of stitching vias along a line.
- **fanout_pads(cmp, dx, dy, layer, width_mils, via_pad_mils, via_hole_mils)** — via + escape track off every netted pad.

## Fab / output
- **get_output_job_containers** — lists OutJob containers (fixed: was broken by an undeclared-Path bug). Found `Daniel_Drone_Controller.OutJob`.
- **run_output_jobs** — execute an OutJob container to generate Gerbers/drill/BOM/etc.
- **check_against_fab(fab)** / **list_fab_profiles** / **apply_fab_profile** — DFM check + fab-floor rules (PCBWay profile present, still UNVERIFIED for 4-layer).

## Known limitations / remaining work
- Diff-pair *object* reader and net-class *member* enumeration: the IPCB script APIs for these are unconfirmed; `get_diff_pair_skew` (name-based) and `get_net_classes` (names) cover most needs.
- Specialized high-speed constraints (diff-pair gap, impedance ohms, matched-length tolerance) aren't directly script-settable in AD25 — use `clone_rule` from a template.
- PCBWay fab profile is UNVERIFIED for this 4-layer board — confirm the numbers before relying on the DFM pass.
- New Python tools require an extension restart + fresh chat to appear; `.pas` changes (readers/fixes) go live per call.

## Added after b6

- **get_diff_pair_skew(tolerance_mils=5)** — intra-pair length skew for differential pairs (inferred from `X_D_P/X_D_N`, `X_P/X_N`, `X+/X-` naming), flags pairs over tolerance. (b6)
- **get_server_status** — now also reports `altium_instances`, `bridge_healthy`, and a note; use it to catch the X2.EXE pileup below. (b8)

## Bridge reliability & operating model (b7 / b8)

The bridge writes `request.json`, shells `X2.EXE -RScriptingSystem:RunScript(...Altium_API>Run)`
to make the running Altium execute the script, then waits for `response.json`. Three
failure modes were diagnosed and mitigated:

1. **New chat shows "no Altium MCP connected."** Server cold-start race — the local
   extension takes a few seconds to register. **Fix: just retry** (or wait ~5 s).
2. **Tools hang mid-session (silent timeouts).** Root cause = **`X2.EXE` process pileup**:
   the `-R` forward spawns a *new* blank Altium instance when the existing one is stuck,
   so requests land in a board-less instance. Also caused by a leftover **error modal**
   in Altium (an open modal freezes the whole script engine). Fixes:
   - b7: the dispatcher's unknown-command branch now returns a JSON error instead of a
     `ShowMessage` **modal** (a modal there froze the bridge until a human clicked OK).
   - b8: the launcher **counts X2.EXE instances before each call and aborts with a clear
     error** ("N Altium instances running - close extras") instead of adding to the pile
     and timing out. `get_server_status` surfaces the count.
   - Manual recovery: close all Altium windows except the one with your PcbDoc (save first).
3. **A tool is missing / behaves like old code.** Stale Python server process.
   **Fix: `get_server_version`** (reports the running build); if it's not the latest,
   restart the extension and open a new chat. Orphaned server processes can be cleared
   by killing `python.exe` processes whose command line contains the extension path.

### Operating cheat-sheet
- New chat won't connect -> **retry**.
- Tools hang -> run **get_server_status**; if `altium_instances` != 1, close extra Altium
  windows; also check Altium for an open error dialog.
- Tool missing / old behavior -> **get_server_version**; if stale, restart extension + new chat.
- After any restart/update -> **run_self_test** (confirms all read tools + a live board).
