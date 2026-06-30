# High-speed rule templates & cloning

## Why this exists

Altium AD25 does **not** expose the per-kind constraint setters (differential-pair
gap, impedance ohms, matched-length tolerance) to DelphiScript — every candidate
property name throws "Undeclared identifier". The values are readable but not
script-writable. See `docs/altium-api-reference.md` for the full investigation.

The workaround is **clone, don't construct**: `IPCB_Rule.Replicate` copies a rule
*with all its constraint values intact*, after which only the name and scope (both
script-settable) are changed. So a correctly-configured rule becomes a stamp.

## The `clone_rule` tool

```
clone_rule(source_name, new_name, scope1="", scope2="", enabled=True)
```

- Copies every constraint from `source_name` (gap, width, ohms, tolerance, ...).
- Sets the new rule's `Name` to `new_name` (must be unique).
- Re-scopes to `scope1` / `scope2` if provided; otherwise keeps the source's scope.
- `enabled=False` makes an **inert template** (DRC-disabled) that won't enforce
  until it is itself cloned with `enabled=True`.

## Template library (inert source rules)

These are built once by cloning the board's existing, correctly-configured rules
into stable `TPL_*` names with `enabled=False`, so schematic regeneration can't
disturb them and they don't double-enforce DRC.

| Template name        | Cloned from                       | Carries                          |
|----------------------|-----------------------------------|----------------------------------|
| `TPL_DIFF_USB2_90R`  | `Diff-USB`                        | diff-pair gap 7/10 mil, width 10/15 mil |
| `TPL_DIFF_CAN_120R`  | `Diff-CAN`                        | diff-pair gap 10/13 mil, width 8/15 mil |
| `TPL_Z_USB2_90R`     | `Schematic Impedance Constraint`  | impedance 85–95 Ω                |
| `TPL_Z_CAN_120R`     | `Schematic Impedance Constraint_1`| impedance 115–125 Ω              |
| `TPL_MATCH_10MIL`    | `Schematic Matched Net Lengths`   | matched-length tolerance 10 mil  |

> Standards that aren't on the board yet (e.g. 100 Ω diff for Ethernet/HDMI/MIPI,
> 50 Ω single-ended) need a one-time manual setup: create one rule in the PCB Rules
> dialog with the right value, name it `TPL_*`, disable it, then clone from it.
> Common targets: USB 2.0 = 90 Ω diff, generic high-speed diff = 100 Ω,
> CAN/FlexRay = 120 Ω diff, single-ended controlled-Z = 50 Ω.

## Stamping out a real rule

To apply a standard to a net class, clone the (disabled) template into an enabled,
re-scoped rule:

```
clone_rule(source_name="TPL_DIFF_USB2_90R",
           new_name="DP_USB2_PORT1",
           scope1="InDifferentialPairClass('USB2_PORT1')",
           enabled=True)
```

The result is a fully-configured, enforcing differential-pair rule — gap and all —
with none of the hidden setters involved.

## What about `create_diff_pair_rule` / `create_impedance_rule` / `create_length_match_rule`?

Those still work and are fine when you don't have a matching template: they create a
correctly-typed, correctly-scoped rule (diff-pair also sets per-layer min/max width)
and leave the specialized constraint at Altium's default with a `constraint_note`.
Use `clone_rule` when you want the exact gap/ohms/tolerance values without a GUI step.
