# Altium DelphiScript API reference (captured from the live install)

Purpose: stop guessing API names. Most bugs in this server came from guessed enum
constants and property names that don't exist. When adding a tool, look here first;
if a value isn't captured yet, get it from Altium's code-completion and add it.

How to capture a list: in Altium's DelphiScript editor, type the prefix (e.g. `eRule_`,
`e...Object`, `eTop`) and code-completion lists every constant. For object properties,
declare the typed variable, type `<var>.`, and read the member list.

---

## TRuleKind — `eRule_*` (PCBServer.PCBRuleFactory argument)  [CONFIRMED]

```
eRule_AcuteAngle            = 21
eRule_AssyTestPointStyle    = 57
eRule_AssyTestPointUsage    = 58
eRule_BackDrilling          = 64
eRule_BoardOutlineClearance = 63
eRule_BrokenNets            = 16
eRule_Clearance             = 0
eRule_ComponentClearance    = 24
eRule_ComponentRotations    = 25
eRule_ConfinementConstraint = 22
eRule_Creepage              = 65
eRule_DaisyChainStubLength  = 5
eRule_DifferentialPairsRouting = 51
eRule_FanoutControl         = 49
eRule_FlightTime_FallingEdge = 37
eRule_FlightTime_RisingEdge  = 36
eRule_HoleToHoleClearance   = 52
eRule_LayerPair             = 48
eRule_LayerStack            = 38
eRule_MaximumViaCount       = 18
eRule_MaxMinHeight          = 50
eRule_MaxMinHoleSize        = 42
eRule_MaxMinImpedance       = 33
eRule_MaxMinLength          = 3
eRule_MaxMinWidth           = 2
eRule_MatchedLengths        = 4
eRule_MaxSlope_FallingEdge  = 40
eRule_MaxSlope_RisingEdge   = 39
eRule_MinimumAnnularRing    = 19
eRule_MinimumSolderMaskSliver = 53
eRule_ModifiedPolygon       = 62
eRule_NetAntennae           = 56
eRule_NetsToIgnore          = 27
eRule_None                  = 61
eRule_Overshoot_FallingEdge = 29
eRule_Overshoot_RisingEdge  = 30
eRule_ParallelSegment       = 1
eRule_PasteMaskExpansion    = 14
eRule_PermittedLayers       = 26
eRule_PolygonConnectStyle   = 20
eRule_PowerPlaneClearance   = 12
eRule_PowerPlaneConnectStyle = 6
eRule_ReturnPath            = 66
eRule_RoutingCornerStyle    = 10
eRule_RoutingLayers         = 9
eRule_RoutingNeckDown       = 67
eRule_RoutingPriority       = 8
eRule_RoutingTopology       = 7
eRule_RoutingViaStyle       = 11
eRule_ShortCircuit          = 15
eRule_SignalBaseValue       = 35
eRule_SignalStimulus        = 28
eRule_SignalTopValue        = 34
eRule_SilkToBoardRegion     = 59
eRule_SilkToSilkClearance   = 55
eRule_SilkToSolderMaskClearance = 54
eRule_SMDNeckDown           = 47
eRule_SMDPADEntry           = 60
eRule_SMDToCorner           = 23
eRule_SMDToPlane            = 46
eRule_SolderMaskExpansion   = 13
eRule_SupplyNets            = 41
eRule_TestPointStyle        = 43
eRule_TestPointUsage        = 44
eRule_UnconnectedPin        = 45
eRule_Undershoot_FallingEdge = 31
eRule_Undershoot_RisingEdge  = 32
eRule_ViasUnderSMD          = 17
eRule_Wirebonding           = 68
eRule_ZAxisClearance        = 69
```

Note the earlier bug: the diff-pair enum is `eRule_DifferentialPairsRouting` (51), NOT
`eRule_DiffPairsRouting`. `eRule_MaxMinImpedance` (33) and `eRule_MatchedLengths` (4) are
correct; their failures were property names, not the enum.

---

## Rule-object properties by rule kind

CONFIRMED (used in working tools):
- Clearance (`eRule_Clearance`): `Gap` (Coord).
- Width (`eRule_MaxMinWidth`): PER-LAYER indexed `MinWidth[LayerID]`, `MaxWidth[LayerID]`,
  `FavoredWidth[LayerID]` (note: "Favored", not "Preferred"). Iterate LayerStack_V7.
- Routing Via Style (`eRule_RoutingViaStyle`): NON-indexed `MinWidth`, `MaxWidth`,
  `PreferedWidth`, `MinHoleWidth`, `MaxHoleWidth`, `PreferedHoleWidth` (note: "Prefered", one r).
- Minimum Annular Ring (`eRule_MinimumAnnularRing`): `Minimum` (Coord).

UNCONFIRMED / NEEDS CODE-COMPLETION (the 3 high-speed rule tools):
- Differential Pairs Routing (`eRule_DifferentialPairsRouting`): tried
  `MinGap/MaxGap/PreferedGap`, `MinWidth/MaxWidth/PreferedWidth`, `MaxUncoupledLength` — verify.
- Max/Min Impedance (`eRule_MaxMinImpedance`): tried `MinImpedance/MaxImpedance` — WRONG
  ("Undeclared identifier: MinImpedance"). Need the real names (maybe `MinimumImpedance`/
  `MaximumImpedance`, or a stackup-profile reference). CAPTURE via `Rule.` code-completion.
- Matched Lengths (`eRule_MatchedLengths`): tried `MatchTolerance` — verify.

To capture: in the script editor, after `Rule := PCBServer.PCBRuleFactory(eRule_XXX);`
type `Rule.` and read the property list; paste it here.

---

## Other lists worth capturing (not yet pulled)

1. Object-set enums for `BoardIterator.AddFilter_ObjectSet(MkSet(...))`: type `e` then look
   for `*Object` — e.g. `eTrackObject, eViaObject, ePadObject, eArcObject, eComponentObject,
   eRegionObject, eFillObject, ePolyObject, eTextObject, eRuleObject, eConnectionObject,
   eNetObject, eDimensionObject, eViolationObject, eComponentBodyObject`. (We GUESSED
   `eConnectionObject` for ratsnest — confirm it exists and what it iterates.)
2. Layer enums (`TLayer`/`TV6_Layer`): `eTopLayer, eBottomLayer, eMidLayer1..30, eTopOverlay,
   eBottomOverlay, eMechanical1..16, eMultiLayer, eTopPaste, eTopSolder, ...` — type `eTop`/`eMid`.
3. Pad/Via testpoint flag members: type `Pad.` and `Via.` and look for `IsTestpoint*` /
   `IsTestPoint(...)` (version-dependent; our `get_testpoints` flagged this as unconfirmed).
4. Connectivity/ratsnest API: how to enumerate unrouted connections (the `get_unrouted_nets`
   tool over-counts plane nets — needs the correct routed-vs-unrouted accessor).
5. `PCBServer.SystemOptions` unit + display settings if we add unit-aware output.

---

## DelphiScript gotchas (hard-won — read before writing scripts)

- **Case-insensitive identifiers**: `BR` and `bR` are the SAME name -> "Identifier redeclared".
- **32-bit integer overflow**: internal coords are ~10^7; squaring them (distance) overflows
  even when vars are declared `Double`. Compute distances in mm (CoordToMMs) then convert back.
- **No nested-routine scope access**: a nested function can't read its enclosing function's
  vars ("Can't access top level variable"). Parse params with an inline loop; make helpers
  top-level procedures that take everything as parameters.
- **No dynamic arrays** (`array of X` fails): use TStringList + integer coords.
- **PreProcess/PostProcess take NO arguments.**
- **Per-function compilation**: a broken identifier in one function only errors when THAT
  function runs; other tools keep working. (That's why one bad rule fn didn't break the rest.)
- Units: `MMsToCoord(mm)`, `CoordToMMs(coord)`; `coord/10000 = mils`; `mils*0.0254 = mm`.

## Deployment / environment gotchas

- Claude Desktop is MSIX-packaged: the running extension loads from
  `AppData\Local\Packages\Claude_*\LocalCache\Roaming\Claude\Claude Extensions\...`, which
  shadows `AppData\Roaming\Claude\Claude Extensions\...`. Sync BOTH copies.
- DelphiScript (`.pas`) is re-read by Altium per tool call -> script fixes are live without a
  restart. Python (`main.py` etc.) is loaded at server start -> Python changes need a restart.
- A chat's MCP tool list is frozen when the chat connects; tools added afterward need a new
  chat (or the stale server process to be cleared) before they're callable.
