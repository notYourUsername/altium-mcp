# altium-mcp roadmap

Condensed from a capability review of the Altium scripting API vs. the tools this server exposes.
Today the server is strong at *reading* design data with a few *create* flows; it is thin on
*modifying* the board and missing whole domains (DRC, BOM/variants, routing, navigation).

## Phase 0 — Foundations (in progress)
Test harness, JSON schemas + fixtures, CI (Tier A), fab-profile scaffold, conventions
(structured errors, mm/mil units, undo wrapping). See `CONVENTIONS.md`.

## Phase 1 — Read coverage & quick wins
- `get_board_info` (size, layer count, origin, units, total thickness)
- net length, net classes, variants, project structure
- **BOM export** (structured JSON/CSV)
- **run DRC + return violations**
- retrofit existing write tools with undo + structured errors

## Phase 2 — Rules engine & fab profiles
- `create/update/delete_design_rule`, `apply_rule_template`
- stackup write, `apply_fab_profile` (drives stackup + rules + drills together)
- DFM check against a fab profile

## Phase 3 — Routing read + review/bring-up reports
- routing/net geometry read, ratsnest/unrouted
- net to probe map, test-point map, continuity matrix, short-candidate finder
- power-rail/decoupling audit, highlight-and-screenshot

## Phase 4 — Editing & navigation
- place component from library (SCH/PCB), align/distribute
- annotation / update-PCB-from-SCH (ECO), SCH<->PCB cross-probe

## Phase 5 — Other applications
- hardware CI (run checks on every commit), `pcb-parts-search` supply-chain pairing,
  firmware pin-map export, auto-docs, reuse templates, library/portfolio governance,
  compliance review, requirements traceability

See `altium-mcp-feature-review.md` and `altium-mcp-build-plan.md` (project folder) for detail and
the autonomous-vs-live-validation split.
