# Altium MCP — placement & routing tools cheat-sheet

All coordinates and sizes are in **mils**, **relative to the board origin** — the
same frame as `get_component_data` and `set_component_position`. So you can read a
part's position and drop vias/tracks relative to it.

> These tools are live after an extension restart + a **new chat** (a chat's tool
> list is fixed when it opens). The via-create / via-delete / net-assignment paths
> were live-validated.

## Placement

**align_components(cmp_designators, axis, mode="avg")**
Snap parts to a shared line. `axis="x"` → common X (vertical column); `axis="y"` →
common Y (horizontal row). `mode`: avg / min / max / first.
```
align_components(["C2","C3","C4"], axis="y")          # line them up in a row
align_components(["R1","R2"], axis="x", mode="first") # share R1's X
```

**distribute_components(cmp_designators, axis, spacing=0)**
Even spacing along an axis, in current order. `spacing` in mils, or 0 = spread
evenly between the two end parts.
```
distribute_components(["C2","C3","C4","C5"], axis="x", spacing=50)
```

**place_relative(cmp_designator, anchor_designator, dx=0, dy=0, anchor_pad="", rotation=-1)**
Drop a part at an offset from another part (or one of its pads). Offsets in mils.
```
# tuck the VCC_RF decoupling cap right at U7 pin 14:
place_relative("C18", "U7", anchor_pad="14", dx=20, dy=0)
```

## Reports

**get_routing_status()**
Routed vs unrouted nets (clean split, no plane miscount) + routed lengths,
longest-first — handy for "what's left to route" and eyeballing length matching.

## Vias & tracks

**add_via(x, y, net="", pad_mils=24, hole_mils=12)**
One through via, optionally on a net. Returns `net_found` so you know the net matched.
```
add_via(1500, 1200, net="GND")        # stitching/thermal via tied to GND
```

**stitch_vias(x1, y1, x2, y2, pitch_mils, net="GND", pad_mils=24, hole_mils=12)**
Row of vias evenly spaced along a line, all on one net. Stitch a pour or guard a trace.
```
# guard the RF feed with a GND via fence beside it:
stitch_vias(1400, 600, 1400, 1400, pitch_mils=40, net="GND")
```

**add_track(x1, y1, x2, y2, layer="top", width_mils=8, net="")**
Straight copper segment. `layer`: top / bottom / mid1 / mid2. Point-to-point assist
(not an autorouter).
```
add_track(1000, 500, 1000, 900, layer="top", width_mils=10, net="GND")
```

**delete_via_near(x, y, tol_mils=20)**
Remove the nearest free (non-component) via — rip up a stray or a stitch.
```
delete_via_near(1500, 1200)
```

## Rules (from earlier)

**clone_rule(source_name, new_name, scope1="", scope2="", enabled=True)**
Copy a fully-configured rule (gap/impedance/tolerance and all) and re-scope it.
Five inert templates already on the board: `TPL_DIFF_USB2_90R`, `TPL_DIFF_CAN_120R`,
`TPL_Z_USB2_90R`, `TPL_Z_CAN_120R`, `TPL_MATCH_10MIL`.
```
clone_rule("TPL_DIFF_USB2_90R", "DP_USB2_PORT1",
           scope1="InDifferentialPairClass('USB2_PORT1')", enabled=True)
```

## Notes
- Sizes default to 24 mil pad / 12 mil hole for vias — pass `pad_mils`/`hole_mils`
  to match your stackup (current board uses ~23.6 mil pad / 11.8 mil hole).
- Via/track tools modify copper; run a DRC (`run_drc`) after a batch.
- These are assists to remove tedium, not a replacement for the Altium autorouter.


---

## Analysis & health tools (added after the placement/routing suite)

**get_server_version()** — running build string (e.g. `2026-06-30-b8`). If older than the
latest deploy, the chat is on a stale server process.

**get_server_status()** — includes `altium_instances` and `bridge_healthy`. If
`altium_instances` isn't 1, close the extra Altium windows (the bridge will hang otherwise).

**run_self_test()** — exercises all read-only bridge commands, returns passed/total. Run it
after any restart/update to confirm the server is healthy and a board is active.

**design_review()** — one-call snapshot: board info + DRC-by-type + unrouted signal count + rule count.

**get_drc_summary(fresh=False)** — DRC violations grouped by type (vs the raw list).
`fresh=True` re-runs the DRC (repours polygons, one undo step).

**get_net_classes()** — object classes; net classes show `kind:"Net"`. Confirms `InNetClass('USB')` names.

**get_routing_status()** — ratsnest-based routed/unrouted split (no plane miscount) + routed lengths.

**get_unrouted_nets()** — per-net outstanding ratsnest; flags `has_pour` and reports
`total_unrouted_signal_nets` (excludes GND/power planes).

**get_diff_pair_skew(tolerance_mils=5)** — intra-pair length skew (from `X_D_P/X_D_N`, `X_P/X_N`
naming), flags pairs over tolerance.
```
get_diff_pair_skew(5)   # e.g. USB_D_P/USB_D_N skew 6.09 mil -> flagged
```

### Health-check sequence after a restart
```
get_server_version   # confirm the expected build
get_server_status    # confirm altium_instances == 1
run_self_test        # confirm all read tools pass
```
If a new chat reports no Altium tools, just retry (server cold-start race). If tools hang
mid-session, run get_server_status and close extra Altium windows. See
`new-tools-catalog.md` -> "Bridge reliability & operating model" for the full picture.

