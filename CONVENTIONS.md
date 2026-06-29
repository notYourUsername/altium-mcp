# Tool conventions

Conventions every new MCP tool should follow. These exist so tools compose well and so the
class of bug behind the core-dielectric fix (silent, untested data loss) can't recur quietly.

## Output
- Return JSON with both **mm and mils** for any geometry/length, and add a matching
  `schemas/<tool>.schema.json` plus a captured fixture in `server/tests/fixtures/`.
- Prefer explicit, typed fields over free-text. Keep additive changes backward compatible.

## Errors
- On failure return `{ "error": "<message>", "code": "<machine_code>", "hint": "<what to do>" }`.
- Detect and distinguish the common cases: `no_document`, `wrong_document_type`,
  `object_not_found`, `nothing_selected`.

## Reads vs writes
- Read tools are safe to call freely.
- Write tools must: (1) offer a **dry-run** that returns the diff without applying,
  (2) wrap the apply in an undo transaction (`PCBServer.PreProcess`/`PostProcess`, or the SCH
  equivalent) so it is one user-undoable step, and (3) require explicit confirmation for
  destructive actions.

## Units & locale
- Internal Altium coordinates are 1/10000 mil. Convert at the boundary; never leak raw coords.
- Parse numbers locale-safely (the comma-decimal bug fixed in upstream PR #3 applies everywhere).

## Testing (definition of done)
- Schema + fixture + passing Tier A test + README entry.
- Write tools also need a live smoke test signed off and a dry-run/undo cycle on a scratch board.
