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

## Useful global constants (from the global code-completion dump)

Coordinate scale (confirms the overflow gotcha): **1 mm = 393701 internal coords**, so
**1 mil = 10000 coords**. Handy literals: `c1_00MM=393701`, `c0_25MM=98425`,
`c0_50MM=196850`, `c10_0MM=3937008`, `c100_0MM=39370078`, `c1000_0MM=393700787`.
Prefer `MMsToCoord()`/`CoordToMMs()` over raw literals.

Layer integer IDs (`c*`): `cBottomLayer=33`, `cBottomOverlay=35`, `cBottomPaste=37`,
`cBottomSolder=39`, `cConnectLayer=76`, `cBackGroundLayer=77`, `cDRCErrorLayer=78`,
`cDRCDetailLayer=79`, `cBottomPadMasterPlot=86`. Sets: `AllLayers`, `AllPrimitives=7766014`,
`AllObjects=8388606`. (Top-side layer IDs + the `e*Layer`/`e*Object` enums are in the `e`
section of the global list — capture when available.)

> The full global scope (thousands of `const`/`function` entries) is always available via
> code-completion; only the curated subsets above are archived here. Don't paste the whole
> thing — the valuable remaining piece is the `e*Object` (iterator filters) and `e*Layer`
> (layer enums) block, plus per-rule-object property lists (via `Rule.` completion).

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


## High-speed rule creation — LIVE-CONFIRMED behavior (AD25)

Confirmed enums (all create successfully via `PCBRuleFactory`):
- Differential Pairs Routing: `eRule_DifferentialPairsRouting`
- Impedance Constraint:       `eRule_MaxMinImpedance`
- Matched Net Lengths:        `eRule_MatchedLengths`

`IPCB_Rule` is one flattened interface, so a property valid for ANY rule kind
compiles regardless of the factory kind; only names that exist on NO kind throw
"Undeclared identifier" — a compiler MODAL at runtime, which surfaces to the MCP
client as a request timeout / "Stream closed".

**Diff-pair WIDTH is settable** and was confirmed landing on the board. It is a
PER-LAYER INDEXED property — identical idiom to the width rule:

```pascal
LS := Board.LayerStack_V7;
Lo := LS.FirstLayer;
while (Lo <> nil) do begin
    Rule.MinWidth[Lo.LayerID] := MMsToCoord(mils * 0.0254);
    Rule.MaxWidth[Lo.LayerID] := MMsToCoord(mils * 0.0254);
    if (Lo = LS.LastLayer) then Break;
    Lo := LS.NextLayer(Lo);
end;
```

Scalar (non-indexed) `Rule.MinWidth := X` on a routing rule throws
**"wrong number of params"** — it MUST be indexed by layer.

**NOT script-settable in AD25** (all throw "Undeclared identifier"; left at Altium
defaults; the reader still parses their values from the descriptor string):
- Diff-pair gap:             `MinGap` / `MaxGap` / `PreferedGap`
- Diff-pair preferred width: `FavoredWidth` and indexed `PreferedWidth` both rejected
- Impedance ohms:            `MinImpedance` / `MaxImpedance`
- Matched-length tolerance:  `MatchTolerance`

These must be set in the PCB Rules dialog. The three `create_*` tools therefore
create a correctly-typed, correctly-scoped rule (diff-pair also sets min/max
width) and return a `constraint_note` telling the user to set the specialized
value in the GUI.



---

# Session findings (builds b1–b8)

## Primitive creation (vias, tracks) — confirmed working
```pascal
Via := PCBServer.PCBObjectFactory(eViaObject, eNoDimension, eCreate_Default);
Via.x := MilsToCoord(xMils) + Board.XOrigin;   // positions are origin-relative mils
Via.y := MilsToCoord(yMils) + Board.YOrigin;
Via.Size := MilsToCoord(padMils);              // pad (outer) diameter
Via.HoleSize := MilsToCoord(holeMils);         // drill
Via.LowLayer := eTopLayer; Via.HighLayer := eBottomLayer;
Board.AddPCBObject(Via);
PCBServer.SendMessageToRobots(Via.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
Track.Layer := eTopLayer;  // or eBottomLayer / eMidLayer1 / eMidLayer2
Track.x1 := ...; Track.y1 := ...; Track.x2 := ...; Track.y2 := ...; Track.Width := MilsToCoord(w);
Board.AddPCBObject(Track);
```
- Net assignment: no confirmed `GetPcbNetByRefName`; instead **iterate `eNetObject`** and match
  `Net.Name`, then `Prim.Net := Net`. `add_via` returns `net_found` to confirm the match.
- Delete a free primitive: iterate `eViaObject`, skip `InComponent`, compare distance in **mm**
  (`CoordToMMs`) to avoid the 32-bit overflow when squaring internal coords.

## Rule property gotchas
- **Width is per-layer indexed**: `Rule.MinWidth[Layer.LayerID]`, `Rule.MaxWidth[Layer.LayerID]`,
  `Rule.FavoredWidth[Layer.LayerID]` (iterate `Board.LayerStack_V7`). Scalar `Rule.MinWidth := X`
  on a routing rule throws **"wrong number of params"**.
- High-speed **constraint setters are not exposed** to DelphiScript in AD25: `MinGap/MaxGap/PreferedGap`,
  `MinImpedance/MaxImpedance`, `MatchTolerance` all throw "Undeclared identifier". The values are
  readable (descriptor / `GetState_DataSummaryString`) but not writable.
- **Workaround = clone**: `NewRule := SourceRule.Replicate;` copies ALL constraints; then set only
  `Name` + `Scope1Expression/Scope2Expression` (both settable) and optionally `DRCEnabled`.
- Confirmed enums: `eRule_DifferentialPairsRouting`, `eRule_MaxMinImpedance`, `eRule_MatchedLengths`,
  `eRule_MaxMinWidth`, `eRule_Clearance`, `eRule_RoutingVias`.

## Class / poured-net reading
- Object classes: iterate `eClassObject`; `Cls.MemberKind = eClassMemberKind_Net` for net classes;
  `Cls.Name`, `Cls.SuperClass`. Differential-pair *object* enumeration and class *member* lists are
  still unconfirmed APIs.
- Poured nets: iterate `ePolyObject`, read `Poly.Net.Name` → set of nets satisfied by a pour
  (used to exclude planes from the unrouted count).

## Bridge architecture & reliability
- Flow: Python writes `C:\Users\Public\altium_mcp\request.json` → shells
  `X2.EXE -RScriptingSystem:RunScript(ProjectName="...Altium_API.PrjScr"^|ProcName="Altium_API>Run")`
  → the running Altium executes the script → writes `response.json` → Python reads it.
- **Never `ShowMessage` on the dispatcher's error paths** — a modal freezes Altium's script engine,
  so every subsequent bridge call hangs until a human clicks OK. Unknown command now returns JSON.
- **X2.EXE pileup**: the `-R` forward can spawn a new blank Altium instance if the existing one is
  stuck; requests then land in a board-less instance (silent timeout). The launcher now counts
  instances and aborts with a clear error when >1; `get_server_status` reports `altium_instances`.
- `.pas` files reload per bridge call (edits go live immediately); `main.py` changes need an
  extension restart + fresh chat. `get_server_version` reports the running build.

