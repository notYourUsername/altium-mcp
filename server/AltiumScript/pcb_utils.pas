// Function to get all unique net names from the current PCB document
function GetAllNets(ROOT_DIR: String): String;
var
    Board       : IPCB_Board;
    Net         : IPCB_Net;
    Iterator    : IPCB_BoardIterator;
    NetsArray   : TStringList; 
    OutputLines : TStringList;
begin
    // Initialize empty array result in case no board is found
    Result := '[]';
    
    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if Board = nil then Exit;

    // Create array for storing unique nets
    NetsArray := TStringList.Create;
    // Set Duplicates property to prevent duplicate net names
    NetsArray.Duplicates := dupIgnore;
    NetsArray.Sorted := True;
    
    try
        // Create the iterator that will look for Net objects only
        Iterator := Board.BoardIterator_Create;
        Iterator.AddFilter_ObjectSet(MkSet(eNetObject));
        Iterator.AddFilter_LayerSet(AllLayers);
        Iterator.AddFilter_Method(eProcessAll);

        // Search for Net objects and get their Net Name values
        Net := Iterator.FirstPCBObject;
        while (Net <> nil) do
        begin
            // Add each net name to the list, duplicates will be ignored
            NetsArray.Add('"' + JSONEscapeString(Net.Name) + '"');
            Net := Iterator.NextPCBObject;
        end;
        Board.BoardIterator_Destroy(Iterator);
        
        // Build the final JSON array
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONArray(NetsArray);
            Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_nets_data.json');
        finally
            OutputLines.Free;
        end;
    finally
        NetsArray.Free;
    end;
end;

// Function to create a net class and add nets to it
function CreateNetClass(ClassName: String; NetNames: TStringList): String;
var
    Board       : IPCB_Board;
    ClassExists : Boolean;
    NetClass    : IPCB_ObjectClass;
    ClassIterator : IPCB_BoardIterator;
    i           : Integer;
    ResultProps : TStringList;
    AddedCount  : Integer;
    OutputLines : TStringList;
begin
    // Initialize result
    ResultProps := TStringList.Create;
    AddedCount := 0;
    ClassExists := False;
    
    try
        // Retrieve the current board
        Board := PCBServer.GetCurrentPCBBoard;
        if (Board = nil) then
        begin
            AddJSONBoolean(ResultProps, 'success', False);
            AddJSONProperty(ResultProps, 'error', 'No PCB document is currently active');
            
            OutputLines := TStringList.Create;
            try
                OutputLines.Text := BuildJSONObject(ResultProps);
                Result := OutputLines.Text;
            finally
                OutputLines.Free;
            end;
            Exit;
        end;
        
        // Search for existing class with the same name
        ClassIterator := Board.BoardIterator_Create;
        ClassIterator.SetState_FilterAll;
        ClassIterator.AddFilter_ObjectSet(MkSet(eClassObject));
        
        NetClass := ClassIterator.FirstPCBObject;
        while (NetClass <> nil) do
        begin
            if (NetClass.MemberKind = eClassMemberKind_Net) and (NetClass.Name = ClassName) then
            begin
                ClassExists := True;
                Break;
            end;
            NetClass := ClassIterator.NextPCBObject;
        end;
        
        // If class doesn't exist, create it
        if not ClassExists then
        begin
            PCBServer.PreProcess;
            NetClass := PCBServer.PCBClassFactoryByClassMember(eClassMemberKind_Net);
            NetClass.SuperClass := False;
            NetClass.Name := ClassName;
            Board.AddPCBObject(NetClass);
            PCBServer.PostProcess;
        end;
        
        // Add nets to the class
        PCBServer.PreProcess;
        for i := 0 to NetNames.Count - 1 do
        begin
            // Add each net to the class
            if NetClass.AddMemberByName(NetNames[i]) then
                AddedCount := AddedCount + 1;
        end;
        PCBServer.PostProcess;
        
        // Clean up iterator
        Board.BoardIterator_Destroy(ClassIterator);
        
        // Build result JSON
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONProperty(ResultProps, 'class_name', ClassName);
        AddJSONBoolean(ResultProps, 'class_created', not ClassExists);
        AddJSONInteger(ResultProps, 'nets_added', AddedCount);
        
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
    end;
end;

// Function to read the DRC violations currently present on the board
function GetDRCViolations(ROOT_DIR): String;
var
    Board       : IPCB_Board;
    Iterator    : IPCB_BoardIterator;
    Violation   : IPCB_Violation;
    ViolArray   : TStringList;
    Props       : TStringList;
    ResultProps : TStringList;
    OutputLines : TStringList;
    BR          : TCoordRect;
    cx, cy      : Integer;
begin
    Result := '';

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"error": "No PCB document is currently active"}';
        Exit;
    end;

    ViolArray := TStringList.Create;
    try
        Iterator := Board.BoardIterator_Create;
        Iterator.AddFilter_ObjectSet(MkSet(eViolationObject));
        Iterator.AddFilter_LayerSet(AllLayers);
        Iterator.AddFilter_Method(eProcessAll);
        Violation := Iterator.FirstPCBObject;
        while (Violation <> nil) do
        begin
            Props := TStringList.Create;
            try
                AddJSONProperty(Props, 'name', Violation.Name);
                AddJSONProperty(Props, 'description', Violation.Description);
                BR := Violation.BoundingRectangle;
                cx := (BR.Left + BR.Right) div 2;
                cy := (BR.Bottom + BR.Top) div 2;
                AddJSONNumber(Props, 'x_mils', CoordToMils(cx));
                AddJSONNumber(Props, 'y_mils', CoordToMils(cy));
                AddJSONNumber(Props, 'x_mm', CoordToMMs(cx));
                AddJSONNumber(Props, 'y_mm', CoordToMMs(cy));
                ViolArray.Add(BuildJSONObject(Props, 1));
            finally
                Props.Free;
            end;
            Violation := Iterator.NextPCBObject;
        end;
        Board.BoardIterator_Destroy(Iterator);

        ResultProps := TStringList.Create;
        try
            AddJSONInteger(ResultProps, 'total_violations', ViolArray.Count);
            ResultProps.Add(BuildJSONArray(ViolArray, 'violations'));
            OutputLines := TStringList.Create;
            try
                OutputLines.Text := BuildJSONObject(ResultProps);
                Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_drc.json');
            finally
                OutputLines.Free;
            end;
        finally
            ResultProps.Free;
        end;
    finally
        ViolArray.Free;
    end;
end;

// Function to run the batch Design Rule Check, then return the resulting violations.
// RunBatchDesignRuleCheck signature (from Altium code completion):
//   RunBatchDesignRuleCheck(ReportFilename: WideString; DRCReportFormat: TDRCReportFileFormat;
//                           DisplayReportFile: LongBool; PublishToWeb: LongBool): LongBool
// Format 0 = first report format; DisplayReportFile False keeps the report window from popping.
function RunDRC(ROOT_DIR): String;
var
    Board  : IPCB_Board;
    PCBDoc : IServerDocument;
    Iter   : IPCB_BoardIterator;
    Poly   : IPCB_Polygon;
begin
    Result := '';

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"error": "No PCB document is currently active"}';
        Exit;
    end;

    // RunBatchDesignRuleCheck resolves the PCB through the FOCUSED project. When
    // this script is launched from its own script project, focus the PCB document
    // first so the DRC finds it within its parent PCB project.
    PCBDoc := Client.GetDocumentByPath(Board.FileName);
    if (PCBDoc <> nil) then
        Client.ShowDocument(PCBDoc);

    // Repour all polygons first so the DRC is accurate and Altium does not prompt
    // about unrepoured polygons (this is what enables a headless run). This MODIFIES
    // the board; wrapped in PreProcess/PostProcess so it is a single undoable step.
    PCBServer.PreProcess;
    try
        Iter := Board.BoardIterator_Create;
        Iter.AddFilter_ObjectSet(MkSet(ePolyObject));
        Iter.AddFilter_LayerSet(AllLayers);
        Iter.AddFilter_Method(eProcessAll);
        Poly := Iter.FirstPCBObject;
        while (Poly <> nil) do
        begin
            Poly.Rebuild;
            Poly := Iter.NextPCBObject;
        end;
        Board.BoardIterator_Destroy(Iter);
    finally
        PCBServer.PostProcess;
    end;
    Board.ViewManager_FullUpdate;

    Board.RunBatchDesignRuleCheck(ROOT_DIR + '\temp_drc_report.html', 0, False, False);

    // Reuse the reader to collect the freshly-created violation objects.
    Result := GetDRCViolations(ROOT_DIR);
end;

// Function to create (or update) a Clearance Constraint design rule.
// Params (from request JSON): rule_name, scope1 (default All), scope2 (default All),
// gap_mils (clearance in mils). Mirrors the create_net_class object-creation idiom.
function ExecuteCreateClearanceRule(RequestData: TStringList): String;
var
    i, ValueStart : Integer;
    RuleName, Scope1, Scope2, ValStr : String;
    GapMils : Double;
    Board   : IPCB_Board;
    Rule    : IPCB_Rule;
    ResultProps : TStringList;
    OutputLines : TStringList;
begin
    RuleName := '';
    Scope1 := 'All';
    Scope2 := 'All';
    GapMils := 10;

    for i := 0 to RequestData.Count - 1 do
    begin
        if (Pos('"rule_name"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            RuleName := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end
        else if (Pos('"scope1"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            Scope1 := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end
        else if (Pos('"scope2"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            Scope2 := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end
        else if (Pos('"gap_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
            ValStr := StringReplace(ValStr, ',', '', REPLACEALL);
            GapMils := StrToFloatDef(ValStr, 10);
        end;
    end;

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;
    if (RuleName = '') then
    begin
        Result := '{"success": false, "error": "No rule_name provided"}';
        Exit;
    end;

    PCBServer.PreProcess;
    Rule := PCBServer.PCBRuleFactory(eRule_Clearance);
    Rule.Name := RuleName;
    Rule.Scope1Expression := Scope1;
    Rule.Scope2Expression := Scope2;
    Rule.Gap := MMsToCoord(GapMils * 0.0254);
    Rule.DRCEnabled := True;
    Board.AddPCBObject(Rule);
    PCBServer.SendMessageToRobots(Rule.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
    PCBServer.PostProcess;

    ResultProps := TStringList.Create;
    try
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONProperty(ResultProps, 'rule_name', RuleName);
        AddJSONProperty(ResultProps, 'rule_kind', 'Clearance');
        AddJSONProperty(ResultProps, 'scope1', Scope1);
        AddJSONProperty(ResultProps, 'scope2', Scope2);
        AddJSONNumber(ResultProps, 'gap_mils', GapMils);
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
    end;
end;

// Function to update an existing Clearance Constraint rule's gap, found by name.
// Params: rule_name, gap_mils.
function ExecuteUpdateClearanceRule(RequestData: TStringList): String;
var
    i, ValueStart : Integer;
    RuleName, ValStr : String;
    GapMils : Double;
    Board : IPCB_Board;
    Iter  : IPCB_BoardIterator;
    Rule, Found : IPCB_Rule;
    ResultProps, OutputLines : TStringList;
begin
    RuleName := '';
    GapMils := -1;

    for i := 0 to RequestData.Count - 1 do
    begin
        if (Pos('"rule_name"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            RuleName := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end
        else if (Pos('"gap_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
            ValStr := StringReplace(ValStr, ',', '', REPLACEALL);
            GapMils := StrToFloatDef(ValStr, -1);
        end;
    end;

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;
    if (RuleName = '') then
    begin
        Result := '{"success": false, "error": "No rule_name provided"}';
        Exit;
    end;
    if (GapMils < 0) then
    begin
        Result := '{"success": false, "error": "No valid gap_mils provided"}';
        Exit;
    end;

    Found := nil;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
    Iter.AddFilter_LayerSet(AllLayers);
    Iter.AddFilter_Method(eProcessAll);
    Rule := Iter.FirstPCBObject;
    while (Rule <> nil) do
    begin
        if (Rule.Name = RuleName) then
        begin
            Found := Rule;
            Break;
        end;
        Rule := Iter.NextPCBObject;
    end;
    Board.BoardIterator_Destroy(Iter);

    if (Found = nil) then
    begin
        Result := '{"success": false, "error": "Rule not found"}';
        Exit;
    end;
    if (Found.GetState_ShortDescriptorString <> 'Clearance Constraint') then
    begin
        Result := '{"success": false, "error": "Named rule is not a Clearance Constraint"}';
        Exit;
    end;

    PCBServer.PreProcess;
    Found.Gap := MMsToCoord(GapMils * 0.0254);
    PCBServer.PostProcess;
    Board.ViewManager_FullUpdate;

    ResultProps := TStringList.Create;
    try
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONProperty(ResultProps, 'rule_name', RuleName);
        AddJSONProperty(ResultProps, 'rule_kind', 'Clearance');
        AddJSONNumber(ResultProps, 'gap_mils', GapMils);
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
    end;
end;

// Function to create a Width Constraint design rule.
// Params: rule_name, scope1 (default All), min_mils, max_mils, preferred_mils.
// (Altium spells the property "PreferedWidth" with one 'r'.)
function ExecuteCreateWidthRule(RequestData: TStringList): String;
var
    i, ValueStart : Integer;
    RuleName, Scope1, ValStr : String;
    MinMils, MaxMils, PrefMils : Double;
    Board : IPCB_Board;
    Rule  : IPCB_Rule;
    LS    : IPCB_LayerStack_V7;
    Lo    : IPCB_LayerObject;
    ResultProps, OutputLines : TStringList;
begin
    RuleName := '';
    Scope1 := 'All';
    MinMils := 6;
    MaxMils := 20;
    PrefMils := 10;

    for i := 0 to RequestData.Count - 1 do
    begin
        if (Pos('"rule_name"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            RuleName := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end
        else if (Pos('"scope1"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            Scope1 := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end
        else if (Pos('"min_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            MinMils := StrToFloatDef(ValStr, 6);
        end
        else if (Pos('"max_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            MaxMils := StrToFloatDef(ValStr, 20);
        end
        else if (Pos('"preferred_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            PrefMils := StrToFloatDef(ValStr, 10);
        end;
    end;

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;
    if (RuleName = '') then
    begin
        Result := '{"success": false, "error": "No rule_name provided"}';
        Exit;
    end;

    PCBServer.PreProcess;
    Rule := PCBServer.PCBRuleFactory(eRule_MaxMinWidth);
    Rule.Name := RuleName;
    Rule.Scope1Expression := Scope1;
    Rule.Scope2Expression := 'All';
    // Width limits are per-layer indexed properties; set them on every copper layer.
    LS := Board.LayerStack_V7;
    if (LS <> nil) then
    begin
        Lo := LS.FirstLayer;
        while (Lo <> nil) do
        begin
            Rule.MinWidth[Lo.LayerID]      := MMsToCoord(MinMils * 0.0254);
            Rule.MaxWidth[Lo.LayerID]      := MMsToCoord(MaxMils * 0.0254);
            Rule.FavoredWidth[Lo.LayerID] := MMsToCoord(PrefMils * 0.0254);
            if (Lo = LS.LastLayer) then Break;
            Lo := LS.NextLayer(Lo);
        end;
    end;
    Rule.DRCEnabled := True;
    Board.AddPCBObject(Rule);
    PCBServer.SendMessageToRobots(Rule.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
    PCBServer.PostProcess;

    ResultProps := TStringList.Create;
    try
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONProperty(ResultProps, 'rule_name', RuleName);
        AddJSONProperty(ResultProps, 'rule_kind', 'Width');
        AddJSONProperty(ResultProps, 'scope1', Scope1);
        AddJSONNumber(ResultProps, 'min_mils', MinMils);
        AddJSONNumber(ResultProps, 'max_mils', MaxMils);
        AddJSONNumber(ResultProps, 'preferred_mils', PrefMils);
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
    end;
end;

// Function to create a Routing Via Style design rule.
// Params: rule_name, scope1 (default All), and independent pad + hole limits:
//   pad_min_mils, pad_max_mils, pad_preferred_mils,
//   hole_min_mils, hole_max_mils, hole_preferred_mils.
// Pad limits map to MinWidth/MaxWidth/PreferedWidth (outer via diameter);
// hole limits map to MinHoleWidth/MaxHoleWidth/PreferedHoleWidth. All three of
// each are set explicitly so the rule does not inherit Altium's defaults.
function ExecuteCreateViaRule(RequestData: TStringList): String;
var
    i, ValueStart : Integer;
    RuleName, Scope1, ValStr : String;
    PadMin, PadMax, PadPref : Double;
    HoleMin, HoleMax, HolePref : Double;
    Board : IPCB_Board;
    Rule  : IPCB_Rule;
    ResultProps, OutputLines : TStringList;
begin
    RuleName := '';
    Scope1 := 'All';
    // Sensible fallbacks (mils); the MCP tool always supplies explicit values.
    PadMin := 24;  PadMax := 24;  PadPref := 24;
    HoleMin := 12; HoleMax := 12; HolePref := 12;

    for i := 0 to RequestData.Count - 1 do
    begin
        if (Pos('"rule_name"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            RuleName := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end
        else if (Pos('"scope1"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            Scope1 := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end
        else if (Pos('"pad_min_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            PadMin := StrToFloatDef(ValStr, PadMin);
        end
        else if (Pos('"pad_max_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            PadMax := StrToFloatDef(ValStr, PadMax);
        end
        else if (Pos('"pad_preferred_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            PadPref := StrToFloatDef(ValStr, PadPref);
        end
        else if (Pos('"hole_min_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            HoleMin := StrToFloatDef(ValStr, HoleMin);
        end
        else if (Pos('"hole_max_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            HoleMax := StrToFloatDef(ValStr, HoleMax);
        end
        else if (Pos('"hole_preferred_mils"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
            HolePref := StrToFloatDef(ValStr, HolePref);
        end;
    end;

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;
    if (RuleName = '') then
    begin
        Result := '{"success": false, "error": "No rule_name provided"}';
        Exit;
    end;

    PCBServer.PreProcess;
    Rule := PCBServer.PCBRuleFactory(eRule_RoutingViaStyle);
    Rule.Name := RuleName;
    Rule.Scope1Expression := Scope1;
    Rule.Scope2Expression := 'All';
    // Via pad (outer) diameter: min / max / preferred (mils -> internal coords)
    Rule.MinWidth := MMsToCoord(PadMin * 0.0254);
    Rule.MaxWidth := MMsToCoord(PadMax * 0.0254);
    Rule.PreferedWidth := MMsToCoord(PadPref * 0.0254);
    // Via hole (inner) diameter: min / max / preferred
    Rule.MinHoleWidth := MMsToCoord(HoleMin * 0.0254);
    Rule.MaxHoleWidth := MMsToCoord(HoleMax * 0.0254);
    Rule.PreferedHoleWidth := MMsToCoord(HolePref * 0.0254);
    Rule.DRCEnabled := True;
    Board.AddPCBObject(Rule);
    PCBServer.SendMessageToRobots(Rule.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
    PCBServer.PostProcess;

    ResultProps := TStringList.Create;
    try
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONProperty(ResultProps, 'rule_name', RuleName);
        AddJSONProperty(ResultProps, 'rule_kind', 'RoutingVias');
        AddJSONProperty(ResultProps, 'scope1', Scope1);
        AddJSONNumber(ResultProps, 'pad_min_mils', PadMin);
        AddJSONNumber(ResultProps, 'pad_max_mils', PadMax);
        AddJSONNumber(ResultProps, 'pad_preferred_mils', PadPref);
        AddJSONNumber(ResultProps, 'hole_min_mils', HoleMin);
        AddJSONNumber(ResultProps, 'hole_max_mils', HoleMax);
        AddJSONNumber(ResultProps, 'hole_preferred_mils', HolePref);
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
    end;
end;

// Function to delete a design rule by its exact name.
// Params: rule_name. Removes the single rule whose Name matches exactly.
function ExecuteDeleteDesignRule(RequestData: TStringList): String;
var
    i, ValueStart : Integer;
    RuleName, DeletedKind : String;
    Board : IPCB_Board;
    Iter  : IPCB_BoardIterator;
    Rule, Found : IPCB_Rule;
    ResultProps, OutputLines : TStringList;
begin
    RuleName := '';

    for i := 0 to RequestData.Count - 1 do
    begin
        if (Pos('"rule_name"', RequestData[i]) > 0) then
        begin
            ValueStart := Pos(':', RequestData[i]) + 1;
            RuleName := TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1));
        end;
    end;

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;
    if (RuleName = '') then
    begin
        Result := '{"success": false, "error": "No rule_name provided"}';
        Exit;
    end;

    Found := nil;
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
    Iter.AddFilter_LayerSet(AllLayers);
    Iter.AddFilter_Method(eProcessAll);
    Rule := Iter.FirstPCBObject;
    while (Rule <> nil) do
    begin
        if (Rule.Name = RuleName) then
        begin
            Found := Rule;
            Break;
        end;
        Rule := Iter.NextPCBObject;
    end;
    Board.BoardIterator_Destroy(Iter);

    if (Found = nil) then
    begin
        Result := '{"success": false, "error": "Rule not found"}';
        Exit;
    end;

    // Capture identifying info before the object is removed.
    DeletedKind := Found.GetState_ShortDescriptorString;

    PCBServer.PreProcess;
    Board.RemovePCBObject(Found);
    PCBServer.SendMessageToRobots(Board.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
    PCBServer.PostProcess;
    Board.ViewManager_FullUpdate;

    ResultProps := TStringList.Create;
    try
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONProperty(ResultProps, 'rule_name', RuleName);
        AddJSONProperty(ResultProps, 'deleted_rule_kind', DeletedKind);
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
    end;
end;

// Function to apply a fab profile: raise the global rule FLOORS to the fab's minimums.
// Params (mm): min_trace_mm, min_space_mm, via_hole_mm, via_pad_mm, annular_mm.
// Touches only All-scoped Width/Clearance/RoutingVias rules (the global defaults) and
// ensures a Minimum Annular Ring rule exists. One undoable step.
function ExecuteApplyFabProfile(RequestData: TStringList): String;
var
    i, ValueStart : Integer;
    ValStr        : String;
    MinTrace, MinSpace, ViaHole, ViaPad, Annular : Double;
    Board   : IPCB_Board;
    Iter    : IPCB_BoardIterator;
    Rule    : IPCB_Rule;
    LS      : IPCB_LayerStack_V7;
    Lo      : IPCB_LayerObject;
    Kind    : String;
    nWidth, nClear, nVia : Integer;
    chg     : Boolean;
    annularRule : IPCB_Rule;
    ResultProps, OutputLines : TStringList;
begin
    MinTrace := 0; MinSpace := 0; ViaHole := 0; ViaPad := 0; Annular := 0;
    for i := 0 to RequestData.Count - 1 do
    begin
        ValueStart := Pos(':', RequestData[i]) + 1;
        ValStr := StringReplace(TrimJSON(Copy(RequestData[i], ValueStart, Length(RequestData[i]) - ValueStart + 1)), ',', '', REPLACEALL);
        if (Pos('"min_trace_mm"', RequestData[i]) > 0) then MinTrace := StrToFloatDef(ValStr, 0)
        else if (Pos('"min_space_mm"', RequestData[i]) > 0) then MinSpace := StrToFloatDef(ValStr, 0)
        else if (Pos('"via_hole_mm"', RequestData[i]) > 0) then ViaHole := StrToFloatDef(ValStr, 0)
        else if (Pos('"via_pad_mm"', RequestData[i]) > 0) then ViaPad := StrToFloatDef(ValStr, 0)
        else if (Pos('"annular_mm"', RequestData[i]) > 0) then Annular := StrToFloatDef(ValStr, 0);
    end;

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;

    nWidth := 0; nClear := 0; nVia := 0;
    annularRule := nil;
    LS := Board.LayerStack_V7;

    PCBServer.PreProcess;

    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
    Iter.AddFilter_LayerSet(AllLayers);
    Iter.AddFilter_Method(eProcessAll);
    Rule := Iter.FirstPCBObject;
    while (Rule <> nil) do
    begin
        Kind := Rule.GetState_ShortDescriptorString;
        if (Kind = 'Width Constraint') and (Rule.Scope1Expression = 'All') and (MinTrace > 0) and (LS <> nil) then
        begin
            // Tighten-only: only raise a layer's floor; never loosen the designer's intent.
            chg := False;
            Lo := LS.FirstLayer;
            while (Lo <> nil) do
            begin
                if (MMsToCoord(MinTrace) > Rule.MinWidth[Lo.LayerID]) then
                begin
                    Rule.MinWidth[Lo.LayerID] := MMsToCoord(MinTrace);
                    chg := True;
                end;
                if (Lo = LS.LastLayer) then Break;
                Lo := LS.NextLayer(Lo);
            end;
            if chg then nWidth := nWidth + 1;
        end
        else if (Kind = 'Clearance Constraint') and (Rule.Scope1Expression = 'All') and (Rule.Scope2Expression = 'All') and (MinSpace > 0) then
        begin
            if (MMsToCoord(MinSpace) > Rule.Gap) then
            begin
                Rule.Gap := MMsToCoord(MinSpace);
                nClear := nClear + 1;
            end;
        end
        else if (Kind = 'Routing Via Style') and (Rule.Scope1Expression = 'All') then
        begin
            chg := False;
            if (ViaHole > 0) and (MMsToCoord(ViaHole) > Rule.MinHoleWidth) then begin Rule.MinHoleWidth := MMsToCoord(ViaHole); chg := True; end;
            if (ViaPad > 0) and (MMsToCoord(ViaPad) > Rule.MinWidth) then begin Rule.MinWidth := MMsToCoord(ViaPad); chg := True; end;
            if chg then nVia := nVia + 1;
        end
        else if (Kind = 'Minimum Annular Ring') then
            annularRule := Rule;
        Rule := Iter.NextPCBObject;
    end;
    Board.BoardIterator_Destroy(Iter);

    if (Annular > 0) then
    begin
        if (annularRule = nil) then
        begin
            annularRule := PCBServer.PCBRuleFactory(eRule_MinimumAnnularRing);
            annularRule.Name := 'FabMinAnnularRing';
            annularRule.Scope1Expression := 'All';
            annularRule.DRCEnabled := True;
            Board.AddPCBObject(annularRule);
            PCBServer.SendMessageToRobots(annularRule.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);
            annularRule.Minimum := MMsToCoord(Annular);
        end
        else if (MMsToCoord(Annular) > annularRule.Minimum) then
            annularRule.Minimum := MMsToCoord(Annular);  // tighten-only
    end;

    PCBServer.PostProcess;
    Board.ViewManager_FullUpdate;

    ResultProps := TStringList.Create;
    try
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONInteger(ResultProps, 'width_rules_updated', nWidth);
        AddJSONInteger(ResultProps, 'clearance_rules_updated', nClear);
        AddJSONInteger(ResultProps, 'via_rules_updated', nVia);
        AddJSONNumber(ResultProps, 'min_trace_mm', MinTrace);
        AddJSONNumber(ResultProps, 'min_space_mm', MinSpace);
        AddJSONNumber(ResultProps, 'via_hole_mm', ViaHole);
        AddJSONNumber(ResultProps, 'via_pad_mm', ViaPad);
        AddJSONNumber(ResultProps, 'annular_mm', Annular);
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
    end;
end;

// Helper: keep the smallest positive coordinate seen (-1 = unset). Top-level so it is
// not a nested routine (DelphiScript nested routines cannot access enclosing scope).
procedure TakeMin(var m: Integer; v: Integer);
begin
    if (v > 0) and ((m < 0) or (v < m)) then m := v;
end;

// Helper: keep the smallest non-negative Double seen (m < 0 = unset). Top-level.
procedure TakeMinD(var m: Double; v: Double);
begin
    if (v >= 0) and ((m < 0) or (v < m)) then m := v;
end;

// Helper: Euclidean distance (internal coords) between two points, as Double. Top-level.
function CoordDist(x1: Integer; y1: Integer; x2: Integer; y2: Integer): Double;
var
    dx, dy : Double;
begin
    dx := x2 - x1;
    dy := y2 - y1;
    Result := Sqrt(dx * dx + dy * dy);
end;

// Helper: shortest distance (internal coords) from point (px,py) to the axis-aligned
// board bounding box [L,R]x[B,T]. For points inside the box (the normal case for copper)
// this is the distance to the nearest of the four edges; for points outside it returns 0.
// NOTE: this approximates the board edge by its bounding rectangle. For a rectangular
// outline it is exact; for a non-rectangular outline it OVER-estimates clearance near
// concave/cut regions. See the FLAG comment in ExecuteFabMeasure. Top-level.
function DistPointToBoxEdge(px: Integer; py: Integer; L: Integer; R: Integer; B: Integer; T: Integer): Double;
var
    dL, dR, dB, dT, m : Double;
begin
    if (px < L) or (px > R) or (py < B) or (py > T) then
    begin
        Result := 0;
        Exit;
    end;
    dL := px - L;
    dR := R - px;
    dB := py - B;
    dT := T - py;
    m := dL;
    if (dR < m) then m := dR;
    if (dB < m) then m := dB;
    if (dT < m) then m := dT;
    Result := m;
end;

// Read-only: measure the board for DFM. Returns smallest observed geometry + current
// rule floors (all in mm). Python (fab.py) compares these against the fab profile.
function ExecuteFabMeasure(RequestData: TStringList): String;
const
    MAX_HOLES = 4000; // O(n^2) guard: 4000 holes -> ~8M pair tests, still fast.
var
    Board : IPCB_Board;
    Iter  : IPCB_BoardIterator;
    Track : IPCB_Track;
    Via   : IPCB_Via;
    Pad   : IPCB_Pad;
    Rule  : IPCB_Rule;
    LS    : IPCB_LayerStack_V7;
    Lo    : IPCB_LayerObject;
    Kind  : String;
    padDim, ann : Integer;
    mTrack, mViaHole, mViaPad, mViaAnn, mPadHole, mPadAnn : Integer;
    rW, rClr, rViaHole, rViaPad, rH2H : Integer;
    nTrack, nVia, nPad : Integer;
    ResultProps, OutputLines : TStringList;
    // Hole-to-hole: collect every hole's center (X,Y) and radius as integer internal
    // coords in parallel TStringLists (no dynamic arrays). Then O(n^2) nearest-neighbour.
    HoleX, HoleY, HoleR : TStringList;
    i, j, nHoles, cx, cy, rad : Integer;
    edgeDist, gap, mH2H, mEdge : Double;
    capped : Boolean;
    BR : TCoordRect;
    bL, bR, bB, bT : Integer;
    haveOutline : Boolean;
begin
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;

    mTrack := -1; mViaHole := -1; mViaPad := -1; mViaAnn := -1; mPadHole := -1; mPadAnn := -1;
    rW := -1; rClr := -1; rViaHole := -1; rViaPad := -1; rH2H := -1;
    nTrack := 0; nVia := 0; nPad := 0;
    mH2H := -1; mEdge := -1; capped := False;
    LS := Board.LayerStack_V7;

    HoleX := TStringList.Create;
    HoleY := TStringList.Create;
    HoleR := TStringList.Create;

    // Board outline bounding box (used to approximate copper-to-edge clearance).
    // FLAG: Board.BoardOutline.BoundingRectangle is the only outline geometry read here.
    // It is exact for rectangular boards but over-estimates clearance for non-rectangular
    // outlines (cutouts, rounded/irregular edges). A precise measure would walk the
    // outline contour segments; that API (IPCB_BoardOutline point/segment accessors) is
    // not confirmed offline, so we use the bounding box and flag the result.
    haveOutline := False;
    bL := 0; bR := 0; bB := 0; bT := 0;
    if (Board.BoardOutline <> nil) then
    begin
        BR := Board.BoardOutline.BoundingRectangle;
        bL := BR.Left; bR := BR.Right; bB := BR.Bottom; bT := BR.Top;
        haveOutline := True;
    end;

    // Tracks (routed copper only -> have a net)
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eTrackObject));
    Iter.AddFilter_LayerSet(AllLayers);
    Iter.AddFilter_Method(eProcessAll);
    Track := Iter.FirstPCBObject;
    while (Track <> nil) do
    begin
        if (Track.Net <> nil) then
        begin
            TakeMin(mTrack, Track.Width);
            nTrack := nTrack + 1;
            // Copper-to-edge: distance from each track endpoint (minus half the track
            // width to reach the copper edge) to the board outline box.
            if (haveOutline) then
            begin
                edgeDist := DistPointToBoxEdge(Track.x1, Track.y1, bL, bR, bB, bT) - (Track.Width div 2);
                if (edgeDist < 0) then edgeDist := 0;
                TakeMinD(mEdge, edgeDist);
                edgeDist := DistPointToBoxEdge(Track.x2, Track.y2, bL, bR, bB, bT) - (Track.Width div 2);
                if (edgeDist < 0) then edgeDist := 0;
                TakeMinD(mEdge, edgeDist);
            end;
        end;
        Track := Iter.NextPCBObject;
    end;
    Board.BoardIterator_Destroy(Iter);

    // Vias
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eViaObject));
    Iter.AddFilter_LayerSet(AllLayers);
    Iter.AddFilter_Method(eProcessAll);
    Via := Iter.FirstPCBObject;
    while (Via <> nil) do
    begin
        TakeMin(mViaHole, Via.HoleSize);
        TakeMin(mViaPad, Via.Size);
        ann := (Via.Size - Via.HoleSize) div 2;
        TakeMin(mViaAnn, ann);
        nVia := nVia + 1;
        // Record the hole (center + radius) for the hole-to-hole pass.
        if (HoleX.Count < MAX_HOLES) then
        begin
            HoleX.Add(IntToStr(Via.x));
            HoleY.Add(IntToStr(Via.y));
            HoleR.Add(IntToStr(Via.HoleSize div 2));
        end
        else
            capped := True;
        // Copper-to-edge for the via pad (pad edge = center distance minus pad radius).
        if (haveOutline) then
        begin
            edgeDist := DistPointToBoxEdge(Via.x, Via.y, bL, bR, bB, bT) - (Via.Size div 2);
            if (edgeDist < 0) then edgeDist := 0;
            TakeMinD(mEdge, edgeDist);
        end;
        Via := Iter.NextPCBObject;
    end;
    Board.BoardIterator_Destroy(Iter);

    // Pads with holes
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(ePadObject));
    Iter.AddFilter_LayerSet(AllLayers);
    Iter.AddFilter_Method(eProcessAll);
    Pad := Iter.FirstPCBObject;
    while (Pad <> nil) do
    begin
        if (Pad.HoleSize > 0) then
        begin
            TakeMin(mPadHole, Pad.HoleSize);
            if (Pad.TopXSize < Pad.TopYSize) then padDim := Pad.TopXSize else padDim := Pad.TopYSize;
            ann := (padDim - Pad.HoleSize) div 2;
            TakeMin(mPadAnn, ann);
            nPad := nPad + 1;
            // Record the pad hole (center + radius) for the hole-to-hole pass.
            if (HoleX.Count < MAX_HOLES) then
            begin
                HoleX.Add(IntToStr(Pad.x));
                HoleY.Add(IntToStr(Pad.y));
                HoleR.Add(IntToStr(Pad.HoleSize div 2));
            end
            else
                capped := True;
            // Copper-to-edge for the pad (use the smaller pad half-dimension as radius).
            if (haveOutline) then
            begin
                edgeDist := DistPointToBoxEdge(Pad.x, Pad.y, bL, bR, bB, bT) - (padDim div 2);
                if (edgeDist < 0) then edgeDist := 0;
                TakeMinD(mEdge, edgeDist);
            end;
        end;
        Pad := Iter.NextPCBObject;
    end;
    Board.BoardIterator_Destroy(Iter);

    // Hole-to-hole: pairwise nearest-neighbour minimum of center-to-center distance
    // minus the two hole radii (edge-to-edge gap). O(n^2) over the collected holes.
    nHoles := HoleX.Count;
    for i := 0 to nHoles - 1 do
    begin
        cx := StrToInt(HoleX[i]);
        cy := StrToInt(HoleY[i]);
        rad := StrToInt(HoleR[i]);
        for j := i + 1 to nHoles - 1 do
        begin
            gap := CoordDist(cx, cy, StrToInt(HoleX[j]), StrToInt(HoleY[j]))
                   - rad - StrToInt(HoleR[j]);
            if (gap < 0) then gap := 0;
            TakeMinD(mH2H, gap);
        end;
    end;
    HoleX.Free;
    HoleY.Free;
    HoleR.Free;

    // Current rule floors
    Iter := Board.BoardIterator_Create;
    Iter.AddFilter_ObjectSet(MkSet(eRuleObject));
    Iter.AddFilter_LayerSet(AllLayers);
    Iter.AddFilter_Method(eProcessAll);
    Rule := Iter.FirstPCBObject;
    while (Rule <> nil) do
    begin
        Kind := Rule.GetState_ShortDescriptorString;
        if (Kind = 'Width Constraint') and (Rule.Scope1Expression = 'All') and (LS <> nil) then
            TakeMin(rW, Rule.MinWidth[LS.FirstLayer.LayerID])
        else if (Kind = 'Clearance Constraint') and (Rule.Scope1Expression = 'All') and (Rule.Scope2Expression = 'All') then
            TakeMin(rClr, Rule.Gap)
        else if (Kind = 'Routing Via Style') and (Rule.Scope1Expression = 'All') then
        begin
            TakeMin(rViaHole, Rule.MinHoleWidth);
            TakeMin(rViaPad, Rule.MinWidth);
        end
        else if (Kind = 'Hole To Hole Clearance') and (Rule.Scope1Expression = 'All') then
            TakeMin(rH2H, Rule.Gap);
        Rule := Iter.NextPCBObject;
    end;
    Board.BoardIterator_Destroy(Iter);

    ResultProps := TStringList.Create;
    try
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONInteger(ResultProps, 'track_count', nTrack);
        AddJSONInteger(ResultProps, 'via_count', nVia);
        AddJSONInteger(ResultProps, 'holed_pad_count', nPad);
        if (mTrack >= 0) then AddJSONNumber(ResultProps, 'min_track_width_mm', CoordToMMs(mTrack));
        if (mViaHole >= 0) then AddJSONNumber(ResultProps, 'min_via_hole_mm', CoordToMMs(mViaHole));
        if (mViaPad >= 0) then AddJSONNumber(ResultProps, 'min_via_pad_mm', CoordToMMs(mViaPad));
        if (mViaAnn >= 0) then AddJSONNumber(ResultProps, 'min_via_annular_mm', CoordToMMs(mViaAnn));
        if (mPadHole >= 0) then AddJSONNumber(ResultProps, 'min_pad_hole_mm', CoordToMMs(mPadHole));
        if (mPadAnn >= 0) then AddJSONNumber(ResultProps, 'min_pad_annular_mm', CoordToMMs(mPadAnn));
        if (mH2H >= 0) then AddJSONNumber(ResultProps, 'min_hole_to_hole_mm', CoordToMMs(Round(mH2H)));
        if (haveOutline and (mEdge >= 0)) then AddJSONNumber(ResultProps, 'min_copper_to_edge_mm', CoordToMMs(Round(mEdge)));
        AddJSONBoolean(ResultProps, 'hole_to_hole_capped', capped);
        if (rW >= 0) then AddJSONNumber(ResultProps, 'rule_min_width_mm', CoordToMMs(rW));
        if (rClr >= 0) then AddJSONNumber(ResultProps, 'rule_min_clearance_mm', CoordToMMs(rClr));
        if (rViaHole >= 0) then AddJSONNumber(ResultProps, 'rule_via_hole_mm', CoordToMMs(rViaHole));
        if (rViaPad >= 0) then AddJSONNumber(ResultProps, 'rule_via_pad_mm', CoordToMMs(rViaPad));
        if (rH2H >= 0) then AddJSONNumber(ResultProps, 'rule_hole_to_hole_mm', CoordToMMs(rH2H));
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
    end;
end;

// Function to get routed copper length per net (sum of tracks + arcs)
function GetNetsWithLength(ROOT_DIR): String;
var
    Board       : IPCB_Board;
    Iterator    : IPCB_BoardIterator;
    Prim        : IPCB_Primitive;
    Track       : IPCB_Track;
    Arc         : IPCB_Arc;
    NetObj      : IPCB_Net;
    NetLengths  : TStringList;
    NetArray    : TStringList;
    Props       : TStringList;
    ResultProps : TStringList;
    OutputLines : TStringList;
    i           : Integer;
    netName     : String;
    addLen      : Double;
    dx, dy      : Double;
    sweep       : Double;
    cur         : Integer;
    totalCoord  : Integer;
begin
    Result := '';

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"error": "No PCB document is currently active"}';
        Exit;
    end;

    NetLengths := TStringList.Create;
    try
        // Accumulate routed length per net as INTEGER internal coords stored in a
        // TStringList (name=value). Integers avoid the locale-sensitive float<->string
        // round-trip that previously produced 'NAN'. addLen is guarded for NaN before
        // rounding. 1 mil = 10000 coords, so Integer holds far more than any net length.
        Iterator := Board.BoardIterator_Create;
        Iterator.AddFilter_ObjectSet(MkSet(eTrackObject, eArcObject));
        Iterator.AddFilter_LayerSet(AllLayers);
        Iterator.AddFilter_Method(eProcessAll);
        Prim := Iterator.FirstPCBObject;
        while (Prim <> nil) do
        begin
            addLen := 0;
            NetObj := nil;
            if (Prim.ObjectId = eTrackObject) then
            begin
                Track := Prim;
                NetObj := Track.Net;
                dx := Track.x2 - Track.x1;
                dy := Track.y2 - Track.y1;
                addLen := Sqrt(dx * dx + dy * dy);
            end
            else if (Prim.ObjectId = eArcObject) then
            begin
                Arc := Prim;
                NetObj := Arc.Net;
                sweep := Arc.EndAngle - Arc.StartAngle;
                if (sweep < 0) then sweep := sweep + 360;
                addLen := 2 * 3.14159265358979 * Arc.Radius * (sweep / 360);
            end;

            // Guard against NaN/invalid contributions
            if (addLen <> addLen) then addLen := 0;

            if (NetObj <> nil) then
            begin
                netName := NetObj.Name;
                cur := StrToIntDef(NetLengths.Values[netName], 0);
                NetLengths.Values[netName] := IntToStr(cur + Round(addLen));
            end;

            Prim := Iterator.NextPCBObject;
        end;
        Board.BoardIterator_Destroy(Iterator);

        // Emit one entry per net with routed copper
        NetArray := TStringList.Create;
        try
            for i := 0 to NetLengths.Count - 1 do
            begin
                netName := NetLengths.Names[i];
                totalCoord := StrToIntDef(NetLengths.Values[netName], 0);
                Props := TStringList.Create;
                try
                    AddJSONProperty(Props, 'net', netName);
                    AddJSONNumber(Props, 'length_mils', totalCoord / 10000);
                    AddJSONNumber(Props, 'length_mm', (totalCoord / 10000) * 0.0254);
                    NetArray.Add(BuildJSONObject(Props, 1));
                finally
                    Props.Free;
                end;
            end;

            ResultProps := TStringList.Create;
            try
                AddJSONInteger(ResultProps, 'total_routed_nets', NetArray.Count);
                ResultProps.Add(BuildJSONArray(NetArray, 'nets'));
                OutputLines := TStringList.Create;
                try
                    OutputLines.Text := BuildJSONObject(ResultProps);
                    Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_nets_length.json');
                finally
                    OutputLines.Free;
                end;
            finally
                ResultProps.Free;
            end;
        finally
            NetArray.Free;
        end;
    finally
        NetLengths.Free;
    end;
end;

// Function to get board-level summary info (size, origin, layers, thickness, units)
function GetBoardInfo(ROOT_DIR): String;
var
    Board          : IPCB_Board;
    TheLayerStack  : IPCB_LayerStack_V7;
    LayerObject    : IPCB_LayerObject;
    DielObj        : IPCB_DielectricObject;
    Props          : TStringList;
    OutputLines    : TStringList;
    BR             : TCoordRect;
    wCoord, hCoord : Integer;
    TotalThk       : Double;
begin
    Result := '';

    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"error": "No PCB document is currently active"}';
        Exit;
    end;

    Props := TStringList.Create;
    try
        AddJSONProperty(Props, 'board_name', ExtractFileName(Board.FileName));

        // Display unit
        if (Board.DisplayUnit = eImperial) then
            AddJSONProperty(Props, 'display_unit', 'mil')
        else
            AddJSONProperty(Props, 'display_unit', 'mm');

        // Board outline bounding box (use Altium's unit-correct converters)
        if (Board.BoardOutline <> nil) then
        begin
            BR := Board.BoardOutline.BoundingRectangle;
            wCoord := BR.Right - BR.Left;
            hCoord := BR.Top - BR.Bottom;
            AddJSONNumber(Props, 'width_mm', CoordToMMs(wCoord));
            AddJSONNumber(Props, 'height_mm', CoordToMMs(hCoord));
            AddJSONNumber(Props, 'width_mils', CoordToMils(wCoord));
            AddJSONNumber(Props, 'height_mils', CoordToMils(hCoord));
        end;

        // Origin
        AddJSONNumber(Props, 'origin_x_mm', CoordToMMs(Board.XOrigin));
        AddJSONNumber(Props, 'origin_y_mm', CoordToMMs(Board.YOrigin));
        AddJSONNumber(Props, 'origin_x_mils', CoordToMils(Board.XOrigin));
        AddJSONNumber(Props, 'origin_y_mils', CoordToMils(Board.YOrigin));

        // Layer count + total physical thickness (copper + dielectric)
        TheLayerStack := Board.LayerStack_V7;
        TotalThk := 0;
        if (TheLayerStack <> nil) then
        begin
            AddJSONInteger(Props, 'signal_layer_count', TheLayerStack.SignalLayerCount);
            LayerObject := TheLayerStack.FirstLayer;
            while (LayerObject <> nil) do
            begin
                TotalThk := TotalThk + (LayerObject.CopperThickness / 10000);
                DielObj := LayerObject.Dielectric;
                if (LayerObject <> TheLayerStack.LastLayer) and (DielObj <> nil) then
                    TotalThk := TotalThk + (DielObj.DielectricHeight / 10000);
                if (LayerObject = TheLayerStack.LastLayer) then Break;
                LayerObject := TheLayerStack.NextLayer(LayerObject);
            end;
        end
        else
            AddJSONInteger(Props, 'signal_layer_count', 0);

        AddJSONNumber(Props, 'total_thickness_mils', TotalThk);
        AddJSONNumber(Props, 'total_thickness_mm', TotalThk * 0.0254);

        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(Props);
            Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_board_info.json');
        finally
            OutputLines.Free;
        end;
    finally
        Props.Free;
    end;
end;

// Function to get detailed layer stackup information
function GetPCBLayerStackup(ROOT_DIR): String;
var
    Board           : IPCB_Board;
    TheLayerStack   : IPCB_LayerStack_V7;
    LayerObject     : IPCB_LayerObject;
    DielObj         : IPCB_DielectricObject;
    StackupArray    : TStringList;
    LayerProps      : TStringList;
    OutputLines     : TStringList;
    TotalThickness  : Double;
    DielHeight      : Double;
    LayerCount      : Integer;
    DielCount       : Integer;
begin
    Result := '';

    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"error": "No PCB document is currently active"}';
        Exit;
    end;

    // Get the layer stack (includes copper + dielectric layer objects)
    TheLayerStack := Board.LayerStack_V7;
    if (TheLayerStack = nil) then
    begin
        Result := '{"error": "No layer stack available"}';
        Exit;
    end;

    // Create arrays for stackup data
    StackupArray := TStringList.Create;
    TotalThickness := 0;
    LayerCount := 0;
    DielCount := 0;

    try
        // Walk the physical stack from the top copper to the bottom copper.
        // For every copper layer EXCEPT the last, the layer's Dielectric property
        // describes the substrate (prepreg or core) that sits between it and the
        // next copper layer down. Altium reports cores with DielectricType =
        // eNoDielectric even though they carry a real material/height/Dk, so we
        // must not gate on the type: any internal gap is a real dielectric.
        LayerObject := TheLayerStack.FirstLayer;
        while (LayerObject <> nil) do
        begin
            LayerProps := TStringList.Create;
            try
                // ---- Copper layer ----
                AddJSONProperty(LayerProps, 'layer_name', LayerObject.Name);
                AddJSONProperty(LayerProps, 'layer_id', Layer2String(LayerObject.LayerID));
                AddJSONProperty(LayerProps, 'material_type', 'Copper');
                AddJSONNumber(LayerProps, 'copper_thickness_mils', LayerObject.CopperThickness / 10000);
                AddJSONNumber(LayerProps, 'copper_thickness_um', LayerObject.CopperThickness / 254);
                TotalThickness := TotalThickness + (LayerObject.CopperThickness / 10000);

                // ---- Dielectric beneath this copper layer ----
                DielObj := LayerObject.Dielectric;
                if (LayerObject <> TheLayerStack.LastLayer) and (DielObj <> nil) then
                begin
                    // Internal gap -> the substrate is always real (prepreg/core),
                    // regardless of how DielectricType is reported.
                    DielHeight := DielObj.DielectricHeight / 10000;
                    case DielObj.DielectricType of
                        eCore: AddJSONProperty(LayerProps, 'dielectric_type', 'Core');
                        ePrePreg: AddJSONProperty(LayerProps, 'dielectric_type', 'PrePreg');
                        eSurfaceMaterial: AddJSONProperty(LayerProps, 'dielectric_type', 'Surface Material');
                    else
                        // eNoDielectric / unset on an internal gap = core substrate
                        AddJSONProperty(LayerProps, 'dielectric_type', 'Core');
                    end;
                    AddJSONProperty(LayerProps, 'dielectric_material', DielObj.DielectricMaterial);
                    AddJSONNumber(LayerProps, 'dielectric_height_mils', DielHeight);
                    AddJSONNumber(LayerProps, 'dielectric_height_um', DielObj.DielectricHeight / 254);
                    AddJSONNumber(LayerProps, 'dielectric_constant', DielObj.DielectricConstant);
                    TotalThickness := TotalThickness + DielHeight;
                    DielCount := DielCount + 1;
                end
                else
                begin
                    // Bottom-most copper: no in-stack dielectric below it.
                    AddJSONProperty(LayerProps, 'dielectric_type', 'No Dielectric');
                    AddJSONProperty(LayerProps, 'dielectric_material', '');
                    AddJSONNumber(LayerProps, 'dielectric_height_mils', 0);
                    AddJSONNumber(LayerProps, 'dielectric_height_um', 0);
                    AddJSONNumber(LayerProps, 'dielectric_constant', 0);
                end;

                AddJSONInteger(LayerProps, 'layer_order', LayerCount + 1);
                StackupArray.Add(BuildJSONObject(LayerProps, 1));
                LayerCount := LayerCount + 1;
            finally
                LayerProps.Free;
            end;

            if (LayerObject = TheLayerStack.LastLayer) then Break;
            LayerObject := TheLayerStack.NextLayer(LayerObject);
        end;

        // Create final stackup object with summary
        LayerProps := TStringList.Create;
        try
            AddJSONInteger(LayerProps, 'total_layers', LayerCount);
            AddJSONInteger(LayerProps, 'total_copper_layers', LayerCount);
            AddJSONInteger(LayerProps, 'total_dielectric_layers', DielCount);
            AddJSONNumber(LayerProps, 'total_thickness_mils', TotalThickness);
            AddJSONNumber(LayerProps, 'total_thickness_mm', TotalThickness * 0.0254);
            AddJSONProperty(LayerProps, 'board_name', ExtractFileName(Board.FileName));
            
            // Add the layers array
            LayerProps.Add(BuildJSONArray(StackupArray, 'layers'));
            
            // Build the final JSON
            OutputLines := TStringList.Create;
            try
                OutputLines.Text := BuildJSONObject(LayerProps);
                Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_stackup_data.json');
            finally
                OutputLines.Free;
            end;
        finally
            LayerProps.Free;
        end;
    finally
        StackupArray.Free;
    end;
end;

// Function to get all layer information from the PCB
function GetPCBLayers(ROOT_DIR: String): String;
var
    Board           : IPCB_Board;
    TheLayerStack   : IPCB_LayerStack_V7;
    LayerObj        : IPCB_LayerObject;
    MechLayer       : IPCB_MechanicalLayer;
    AllLayersArray  : TStringList;
    CopperArray     : TStringList;
    MechArray       : TStringList;
    OtherArray      : TStringList;
    LayerProps      : TStringList;
    i               : Integer;
    OutputLines     : TStringList;
begin
    Result := '';

    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '[]';
        Exit;
    end;
    
    // Get the layer stack
    TheLayerStack := Board.LayerStack_V7;
    if (TheLayerStack = nil) then
    begin
        Result := '[]';
        Exit;
    end;

    // Create arrays for different layer categories
    AllLayersArray := TStringList.Create;
    CopperArray := TStringList.Create;
    MechArray := TStringList.Create;
    OtherArray := TStringList.Create;
    
    try
        // Process copper (electrical) layers
        LayerObj := TheLayerStack.FirstLayer;
        while (LayerObj <> nil) do
        begin
            // Create layer properties
            LayerProps := TStringList.Create;
            try
                // Add properties
                AddJSONProperty(LayerProps, 'name', LayerObj.Name);
                AddJSONProperty(LayerProps, 'layer_id', IntToStr(LayerObj.V6_LayerID));
                AddJSONProperty(LayerProps, 'layer_type', 'copper');

                if LayerSet.SignalLayers.Contains(LayerObj.V6_LayerID) then
                    AddJSONProperty(LayerProps, 'is_signal', 'true', False)
                else
                    AddJSONProperty(LayerProps, 'is_signal', 'false', False);

                if not LayerSet.SignalLayers.Contains(LayerObj.V6_LayerID) then
                    AddJSONProperty(LayerProps, 'is_plane', 'true', False)
                else
                    AddJSONProperty(LayerProps, 'is_plane', 'false', False);

                AddJSONBoolean(LayerProps, 'is_displayed', LayerObj.IsDisplayed[Board]);
                AddJSONBoolean(LayerProps, 'is_enabled', True);
                AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[LayerObj.LayerID]));
                
                // Add to copper array
                CopperArray.Add(BuildJSONObject(LayerProps, 1));
            finally
                LayerProps.Free;
            end;
            
            LayerObj := TheLayerStack.NextLayer(LayerObj);
        end;
        
        // Process mechanical layers
        for i := 1 to 32 do
        begin
            MechLayer := TheLayerStack.LayerObject_V7[ILayer.MechanicalLayer(i)];
            
            if MechLayer.MechanicalLayerEnabled then
            begin
                // Create layer properties
                LayerProps := TStringList.Create;
                try
                    // Add properties
                    AddJSONProperty(LayerProps, 'name', MechLayer.Name);
                    AddJSONProperty(LayerProps, 'layer_id', IntToStr(MechLayer.V6_LayerID));
                    AddJSONProperty(LayerProps, 'layer_type', 'mechanical');
                    AddJSONProperty(LayerProps, 'mechanical_number', IntToStr(i));
                    AddJSONBoolean(LayerProps, 'is_displayed', MechLayer.IsDisplayed[Board]);
                    AddJSONBoolean(LayerProps, 'is_enabled', MechLayer.MechanicalLayerEnabled);
                    AddJSONBoolean(LayerProps, 'link_to_sheet', MechLayer.LinkToSheet);
                    AddJSONBoolean(LayerProps, 'is_paired', Board.MechanicalPairs.LayerUsed(ILayer.MechanicalLayer(i)));
                    AddJSONProperty(LayerProps, 'color', ColorToString(PCBServer.SystemOptions.LayerColors[MechLayer.V6_LayerID]));
                    
                    // If layer is paired, add the pair information
                    if Board.MechanicalPairs.LayerUsed(ILayer.MechanicalLayer(i)) then
                    begin
                        // Could add pair info here if Altium API provides it
                    end;
                    
                    // Add to mechanical array
                    MechArray.Add(BuildJSONObject(LayerProps, 1));
                finally
                    LayerProps.Free;
                end;
            end;
        end;
        
        // Process other special layers
        // Top Overlay
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Top Overlay');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Top Overlay')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'overlay');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Top Overlay')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Top Overlay')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Bottom Overlay
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Bottom Overlay');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Bottom Overlay')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'overlay');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Bottom Overlay')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Bottom Overlay')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Top Solder Mask
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Top Solder Mask');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Top Solder Mask')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'solder_mask');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Top Solder Mask')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Top Solder Mask')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Bottom Solder Mask
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Bottom Solder Mask');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Bottom Solder Mask')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'solder_mask');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Bottom Solder Mask')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Bottom Solder Mask')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Top Paste
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Top Paste');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Top Paste')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'paste');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Top Paste')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Top Paste')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Bottom Paste
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Bottom Paste');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Bottom Paste')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'paste');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Bottom Paste')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Bottom Paste')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Drill Guide
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Drill Guide');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Drill Guide')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'drill');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Drill Guide')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Drill Guide')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Drill Drawing
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Drill Drawing');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Drill Drawing')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'drill');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Drill Drawing')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Drill Drawing')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Multi Layer
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Multi Layer');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Multi Layer')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'multi');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Multi Layer')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Multi Layer')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Keep Out Layer
        LayerProps := TStringList.Create;
        try
            AddJSONProperty(LayerProps, 'name', 'Keep Out Layer');
            AddJSONProperty(LayerProps, 'layer_id', IntToStr(String2Layer('Keep Out Layer')));
            AddJSONProperty(LayerProps, 'layer_type', 'special');
            AddJSONProperty(LayerProps, 'special_type', 'keepout');
            AddJSONBoolean(LayerProps, 'is_displayed', Board.LayerIsDisplayed[String2Layer('Keep Out Layer')]);
            AddJSONProperty(LayerProps, 'color', ColorToString(Board.LayerColor[String2Layer('Keep Out Layer')]));
            OtherArray.Add(BuildJSONObject(LayerProps, 1));
        finally
            LayerProps.Free;
        end;
        
        // Add additional info for the complete layer response
        LayerProps := TStringList.Create;
        try
            // Add summary information
            AddJSONInteger(LayerProps, 'copper_layers_count', TheLayerStack.LayersInStackCount);
            AddJSONInteger(LayerProps, 'signal_layers_count', TheLayerStack.SignalLayerCount);
            AddJSONInteger(LayerProps, 'internal_planes_count', TheLayerStack.LayersInStackCount - TheLayerStack.SignalLayerCount);
            
            // Get the number of enabled mechanical layers
            i := 0;
            for i := 1 to 32 do
                if TheLayerStack.LayerObject_V7[ILayer.MechanicalLayer(i)].MechanicalLayerEnabled then
                    i := i + 1;
            AddJSONInteger(LayerProps, 'mechanical_layers_count', i);
            
            // Add the layer arrays
            LayerProps.Add(BuildJSONArray(CopperArray, 'copper_layers'));
            LayerProps.Add(BuildJSONArray(MechArray, 'mechanical_layers'));
            LayerProps.Add(BuildJSONArray(OtherArray, 'special_layers'));
            
            // Build the final JSON
            OutputLines := TStringList.Create;
            try
                OutputLines.Text := BuildJSONObject(LayerProps);
                Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_layers_data.json');
            finally
                OutputLines.Free;
            end;
        finally
            LayerProps.Free;
        end;
    finally
        AllLayersArray.Free;
        CopperArray.Free;
        MechArray.Free;
        OtherArray.Free;
    end;
end;

// Function to set layer visibility (only specified layers visible)
// Function to set layer visibility with two modes:
// - visible=true: Show only specified layers, hide all others
// - visible=false: Hide specified layers, leave others unchanged
function SetPCBLayerVisibility(LayerNamesList: TStringList; Visible: Boolean): String;
var
    Board          : IPCB_Board;
    TheLayerStack  : IPCB_LayerStack_V7;
    LayerObj       : IPCB_LayerObject;
    MechLayer      : IPCB_MechanicalLayer;
    ResultProps    : TStringList;
    OutputLines    : TStringList;
    i, j           : Integer;
    LayerName      : String;
    LayerID        : TLayer;
    FoundCount     : Integer;
    NotFoundList   : TStringList;
    FoundLayers    : TStringList;
begin
    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;
    
    // Get the layer stack
    TheLayerStack := Board.LayerStack_V7;
    if (TheLayerStack = nil) then
    begin
        Result := '{"success": false, "error": "Failed to retrieve layer stack"}';
        Exit;
    end;
    
    // Create lists for tracking results
    ResultProps := TStringList.Create;
    NotFoundList := TStringList.Create;
    FoundLayers := TStringList.Create;
    FoundCount := 0;
    
    try
        // First phase: identify all specified layers
        for i := 0 to LayerNamesList.Count - 1 do
        begin
            LayerName := LayerNamesList[i];
            
            // Try to find the layer by name
            // First check special layers (since they have specific names)
            if (LayerName = 'Top Overlay') or 
               (LayerName = 'Bottom Overlay') or
               (LayerName = 'Top Solder Mask') or
               (LayerName = 'Bottom Solder Mask') or
               (LayerName = 'Top Paste') or
               (LayerName = 'Bottom Paste') or
               (LayerName = 'Drill Guide') or
               (LayerName = 'Drill Drawing') or
               (LayerName = 'Multi Layer') or
               (LayerName = 'Keep Out Layer') then
            begin
                // Get layer ID from name
                LayerID := String2Layer(LayerName);
                if (LayerID <> eNoLayer) then
                begin
                    FoundLayers.Add(IntToStr(LayerID));
                    FoundCount := FoundCount + 1;
                end
                else
                    NotFoundList.Add('"' + JSONEscapeString(LayerName) + '"');
                
                continue;
            end;
            
            // Check copper layers
            LayerObj := TheLayerStack.FirstLayer;
            j := 1;
            
            while (LayerObj <> nil) do
            begin
                if (LayerObj.Name = LayerName) then
                begin
                    FoundLayers.Add(IntToStr(LayerObj.V6_LayerID));
                    FoundCount := FoundCount + 1;
                    break;
                end;
                
                Inc(j);
                LayerObj := TheLayerStack.NextLayer(LayerObj);
            end;
            
            // If we found the layer in copper layers, continue to next layer name
            if (LayerObj <> nil) then
                continue;
            
            // Check mechanical layers (they can have custom names)
            for j := 1 to 32 do
            begin
                MechLayer := TheLayerStack.LayerObject_V7[ILayer.MechanicalLayer(j)];
                
                if MechLayer.MechanicalLayerEnabled and (MechLayer.Name = LayerName) then
                begin
                    FoundLayers.Add(IntToStr(MechLayer.V6_LayerID));
                    FoundCount := FoundCount + 1;
                    break;
                end;
            end;
            
            // If we've checked all layer types and didn't find a match, add to not found list
            if j > 32 then
                NotFoundList.Add('"' + JSONEscapeString(LayerName) + '"');
        end;
        
        // Second phase: set visibility for all layers based on mode
        if Visible then
        begin
            // Visibility mode: show only specified layers, hide all others
            
            // For copper layers
            LayerObj := TheLayerStack.FirstLayer;
            while (LayerObj <> nil) do
            begin
                // Check if this layer is in our found list
                if (FoundLayers.IndexOf(IntToStr(LayerObj.V6_LayerID)) >= 0) then
                    LayerObj.IsDisplayed[Board] := True
                else
                    LayerObj.IsDisplayed[Board] := False;
                
                LayerObj := TheLayerStack.NextLayer(LayerObj);
            end;
            
            // For mechanical layers
            for j := 1 to 32 do
            begin
                MechLayer := TheLayerStack.LayerObject_V7[ILayer.MechanicalLayer(j)];
                
                if MechLayer.MechanicalLayerEnabled then
                begin
                    if (FoundLayers.IndexOf(IntToStr(MechLayer.V6_LayerID)) >= 0) then
                        MechLayer.IsDisplayed[Board] := True
                    else
                        MechLayer.IsDisplayed[Board] := False;
                end;
            end;
            
            // For special layers
            for j := 1 to 10 do
            begin
                case j of
                    1: LayerID := String2Layer('Top Overlay');
                    2: LayerID := String2Layer('Bottom Overlay');
                    3: LayerID := String2Layer('Top Solder Mask');
                    4: LayerID := String2Layer('Bottom Solder Mask');
                    5: LayerID := String2Layer('Top Paste');
                    6: LayerID := String2Layer('Bottom Paste');
                    7: LayerID := String2Layer('Drill Guide');
                    8: LayerID := String2Layer('Drill Drawing');
                    9: LayerID := String2Layer('Multi Layer');
                    10: LayerID := String2Layer('Keep Out Layer');
                end;
                
                if (FoundLayers.IndexOf(IntToStr(LayerID)) >= 0) then
                    Board.LayerIsDisplayed[LayerID] := True
                else
                    Board.LayerIsDisplayed[LayerID] := False;
            end;
        end
        else
        begin
            // Hide mode: only hide specified layers, leave others unchanged
            
            // For copper layers
            LayerObj := TheLayerStack.FirstLayer;
            while (LayerObj <> nil) do
            begin
                // Check if this layer is in our found list
                if (FoundLayers.IndexOf(IntToStr(LayerObj.V6_LayerID)) >= 0) then
                    LayerObj.IsDisplayed[Board] := False;
                
                LayerObj := TheLayerStack.NextLayer(LayerObj);
            end;
            
            // For mechanical layers
            for j := 1 to 32 do
            begin
                MechLayer := TheLayerStack.LayerObject_V7[ILayer.MechanicalLayer(j)];
                
                if MechLayer.MechanicalLayerEnabled then
                begin
                    if (FoundLayers.IndexOf(IntToStr(MechLayer.V6_LayerID)) >= 0) then
                        MechLayer.IsDisplayed[Board] := False;
                end;
            end;
            
            // For special layers
            for j := 1 to 10 do
            begin
                case j of
                    1: LayerID := String2Layer('Top Overlay');
                    2: LayerID := String2Layer('Bottom Overlay');
                    3: LayerID := String2Layer('Top Solder Mask');
                    4: LayerID := String2Layer('Bottom Solder Mask');
                    5: LayerID := String2Layer('Top Paste');
                    6: LayerID := String2Layer('Bottom Paste');
                    7: LayerID := String2Layer('Drill Guide');
                    8: LayerID := String2Layer('Drill Drawing');
                    9: LayerID := String2Layer('Multi Layer');
                    10: LayerID := String2Layer('Keep Out Layer');
                end;
                
                if (FoundLayers.IndexOf(IntToStr(LayerID)) >= 0) then
                    Board.LayerIsDisplayed[LayerID] := False;
            end;
        end;
        
        // Update the display
        Board.ViewManager_FullUpdate;
        Board.ViewManager_UpdateLayerTabs;
        
        // Create result JSON
        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONInteger(ResultProps, 'updated_count', FoundCount);
        
        // Add missing layers array
        if (NotFoundList.Count > 0) then
            ResultProps.Add(BuildJSONArray(NotFoundList, 'not_found_layers'))
        else
            ResultProps.Add('"not_found_layers": []');
        
        // Build final JSON
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
        NotFoundList.Free;
        FoundLayers.Free;
    end;
end;

// Function to get all PCB rules
function GetPCBRules(ROOT_DIR: String): String;
Var
    Board         : IPCB_Board;
    Rule          : IPCB_Rule;
    BoardIterator : IPCB_BoardIterator;
    RulesArray    : TStringList;
    RuleProps     : TStringList;
    OutputLines   : TStringList;
begin
    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = Nil) then
    begin
        Result := '[]';
        Exit;
    end;

    // Create array for rules
    RulesArray := TStringList.Create;
    
    try
        // Retrieve the iterator
        BoardIterator := Board.BoardIterator_Create;
        BoardIterator.AddFilter_ObjectSet(MkSet(eRuleObject));
        BoardIterator.AddFilter_LayerSet(AllLayers);
        BoardIterator.AddFilter_Method(eProcessAll);

        // Process each rule
        Rule := BoardIterator.FirstPCBObject;
        while (Rule <> Nil) do
        begin
            // Create rule properties
            RuleProps := TStringList.Create;
            try
                // Add rule name + descriptor
                AddJSONProperty(RuleProps, 'rule_name', Rule.Name);
                AddJSONProperty(RuleProps, 'descriptor', Rule.Descriptor);
                AddJSONProperty(RuleProps, 'rule_kind', Rule.GetState_ShortDescriptorString);
                AddJSONProperty(RuleProps, 'filter1', Rule.Scope1Expression);
                AddJSONProperty(RuleProps, 'filter2', Rule.Scope2Expression);

                // Add to rules array
                RulesArray.Add(BuildJSONObject(RuleProps, 1));
            finally
                RuleProps.Free;
            end;
            
            // Move to next rule
            Rule := BoardIterator.NextPCBObject;
        end;

        // Clean up the iterator
        Board.BoardIterator_Destroy(BoardIterator);
        
        // Build the final JSON array
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONArray(RulesArray);
            Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_rules_data.json');
        finally
            OutputLines.Free;
        end;
    finally
        RulesArray.Free;
    end;
end;

// Function to get all component data from the PCB
function GetAllComponentData(ROOT_DIR: String, SelectedOnly: Boolean = False): String;
var
    Board       : IPCB_Board;
    Iterator    : IPCB_BoardIterator;
    Component   : IPCB_Component;
    ComponentsArray : TStringList;
    ComponentProps : TStringList;
    Rect        : TCoordRect;
    xorigin, yorigin : Integer;
    i           : Integer;
    ComponentCount : Integer;
    OutputLines : TStringList;
begin
    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '[]';
        Exit;
    end;
    
    // Get board origin coordinates
    xorigin := Board.XOrigin;
    yorigin := Board.YOrigin;

    // Create array for components
    ComponentsArray := TStringList.Create;
    
    try
        // Create an iterator to find all components
        Iterator := Board.BoardIterator_Create;
        Iterator.AddFilter_ObjectSet(MkSet(eComponentObject));
        Iterator.AddFilter_IPCB_LayerSet(LayerSet.AllLayers);
        Iterator.AddFilter_Method(eProcessAll);

        // Process each component
        Component := Iterator.FirstPCBObject;
        while (Component <> Nil) do
        begin
            // Process either all components or only selected ones
            if ((not SelectedOnly) or (SelectedOnly and Component.Selected)) then
            begin
                // Create component properties
                ComponentProps := TStringList.Create;
                try
                    // Get bounds
                    Rect := Component.BoundingRectangleNoNameComment;
                    
                    // Add properties
                    AddJSONProperty(ComponentProps, 'designator', Component.Name.Text);
                    AddJSONProperty(ComponentProps, 'name', Component.Identifier);
                    AddJSONProperty(ComponentProps, 'description', Component.SourceDescription);
                    AddJSONProperty(ComponentProps, 'footprint', Component.Pattern);
                    AddJSONProperty(ComponentProps, 'layer', Layer2String(Component.Layer));
                    AddJSONNumber(ComponentProps, 'x', CoordToMils(Component.x - xorigin));
                    AddJSONNumber(ComponentProps, 'y', CoordToMils(Component.y - yorigin));
                    AddJSONNumber(ComponentProps, 'width', CoordToMils(Rect.Right - Rect.Left));
                    AddJSONNumber(ComponentProps, 'height', CoordToMils(Rect.Bottom - Rect.Top));
                    AddJSONNumber(ComponentProps, 'rotation', Component.Rotation);
                    
                    // Add to components array
                    ComponentsArray.Add(BuildJSONObject(ComponentProps, 1));
                finally
                    ComponentProps.Free;
                end;
            end;
            
            // Move to next component
            Component := Iterator.NextPCBObject;
        end;

        // Clean up the iterator
        Board.BoardIterator_Destroy(Iterator);
        
        // Build the final JSON array
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONArray(ComponentsArray);
            Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_component_data.json');
        finally
            OutputLines.Free;
        end;
    finally
        ComponentsArray.Free;
    end;
end;

// Example refactored function using the new JSON utilities
function GetSelectedComponentsCoordinates(ROOT_DIR: String): String;
var
    Board       : IPCB_Board;
    Component   : IPCB_Component;
    Rect        : TCoordRect;
    xorigin, yorigin : Integer;
    ComponentsArray : TStringList;
    ComponentProps : TStringList;
    OutputLines : TStringList;
    i : Integer;
begin
    Result := '';

    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if Board = nil then Exit;

    // Get board origin coordinates
    xorigin := Board.XOrigin;
    yorigin := Board.YOrigin;

    // Create output and components array
    OutputLines := TStringList.Create;
    ComponentsArray := TStringList.Create;
    
    try
        // Process each selected component
        for i := 0 to Board.SelectecObjectCount - 1 do
        begin
            // Only process selected components
            if Board.SelectecObject[i].ObjectId = eComponentObject then
            begin
                // Cast to component type
                Component := Board.SelectecObject[i];
                
                // Get component bounds
                Rect := Component.BoundingRectangleNoNameComment;
                
                // Create component properties
                ComponentProps := TStringList.Create;
                try
                    // Add component properties
                    AddJSONProperty(ComponentProps, 'designator', Component.Name.Text);
                    AddJSONNumber(ComponentProps, 'x', CoordToMils(Component.x - xorigin));
                    AddJSONNumber(ComponentProps, 'y', CoordToMils(Component.y - yorigin));
                    AddJSONNumber(ComponentProps, 'width', CoordToMils(Rect.Right - Rect.Left));
                    AddJSONNumber(ComponentProps, 'height', CoordToMils(Rect.Bottom - Rect.Top));
                    AddJSONNumber(ComponentProps, 'rotation', Component.Rotation);
                    
                    // Add component JSON to array
                    ComponentsArray.Add(BuildJSONObject(ComponentProps, 1));
                finally
                    ComponentProps.Free;
                end;
            end;
        end;
        
        // If components found, build array
        if ComponentsArray.Count > 0 then
            Result := BuildJSONArray(ComponentsArray)
        else
            Result := '[]';
            
        // For consistency with existing code, write to file and read back
        OutputLines.Text := Result;
        Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_selected_components.json');
    finally
        ComponentsArray.Free;
        OutputLines.Free;
    end;
end;

// Function to get pin data for specified components
function GetComponentPinsFromList(ROOT_DIR: String; DesignatorsList: TStringList): String;
var
    Board           : IPCB_Board;
    Component       : IPCB_Component;
    ComponentsArray : TStringList;
    CompProps       : TStringList;
    PinsArray       : TStringList;
    GrpIter         : IPCB_GroupIterator;
    Pad             : IPCB_Pad;
    NetName         : String;
    xorigin, yorigin : Integer;
    PinProps        : TStringList;
    PinCount, PinsProcessed : Integer;
    Designator      : String;
    i               : Integer;
    OutputLines     : TStringList;
begin
    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '[]';
        Exit;
    end;
    
    // Get board origin coordinates
    xorigin := Board.XOrigin;
    yorigin := Board.YOrigin;

    // Create array for components
    ComponentsArray := TStringList.Create;
    
    try
        // Process each designator
        for i := 0 to DesignatorsList.Count - 1 do
        begin
            Designator := Trim(DesignatorsList[i]);
            
            // Use direct function to get component by designator
            Component := Board.GetPcbComponentByRefDes(Designator);
            
            if (Component <> Nil) then
            begin
                // Create component properties
                CompProps := TStringList.Create;
                PinsArray := TStringList.Create;
                
                try
                    // Add designator to component
                    AddJSONProperty(CompProps, 'designator', Component.Name.Text);
                    
                    // Create pad iterator
                    GrpIter := Component.GroupIterator_Create;
                    GrpIter.SetState_FilterAll;
                    GrpIter.AddFilter_ObjectSet(MkSet(ePadObject));
                    
                    // Count pins
                    PinCount := 0;
                    Pad := GrpIter.FirstPCBObject;
                    while (Pad <> Nil) do
                    begin
                        if Pad.InComponent then
                            PinCount := PinCount + 1;
                        Pad := GrpIter.NextPCBObject;
                    end;
                    
                    // Reset iterator
                    Component.GroupIterator_Destroy(GrpIter);
                    GrpIter := Component.GroupIterator_Create;
                    GrpIter.SetState_FilterAll;
                    GrpIter.AddFilter_ObjectSet(MkSet(ePadObject));
                    
                    // Process each pad
                    PinsProcessed := 0;
                    Pad := GrpIter.FirstPCBObject;
                    while (Pad <> Nil) do
                    begin
                        if Pad.InComponent then
                        begin
                            // Get net name if connected
                            if (Pad.Net <> Nil) then
                                NetName := Pad.Net.Name
                            else
                                NetName := '';
                                
                            // Create pin properties
                            PinProps := TStringList.Create;
                            try
                                AddJSONProperty(PinProps, 'name', Pad.Name);
                                AddJSONProperty(PinProps, 'net', NetName);
                                AddJSONNumber(PinProps, 'x', CoordToMils(Pad.x - xorigin));
                                AddJSONNumber(PinProps, 'y', CoordToMils(Pad.y - yorigin));
                                AddJSONNumber(PinProps, 'rotation', Pad.Rotation);
                                AddJSONProperty(PinProps, 'layer', Layer2String(Pad.Layer));
                                AddJSONNumber(PinProps, 'width', CoordToMils(Pad.XSizeOnLayer[Pad.Layer]));
                                AddJSONNumber(PinProps, 'height', CoordToMils(Pad.YSizeOnLayer[Pad.Layer]));
                                AddJSONProperty(PinProps, 'shape', ShapeToString(Pad.ShapeOnLayer[Pad.Layer]));
                                
                                // Add to pins array
                                PinsArray.Add(BuildJSONObject(PinProps, 3));
                                
                                // Increment counter
                                PinsProcessed := PinsProcessed + 1;
                            finally
                                PinProps.Free;
                            end;
                        end;
                        
                        Pad := GrpIter.NextPCBObject;
                    end;
                    
                    // Clean up iterator
                    Component.GroupIterator_Destroy(GrpIter);
                    
                    // Add pins array to component
                    CompProps.Add(BuildJSONArray(PinsArray, 'pins', 1));
                    
                    // Add to components array
                    ComponentsArray.Add(BuildJSONObject(CompProps, 1));
                finally
                    CompProps.Free;
                    PinsArray.Free;
                end;
            end
            else
            begin
                // Component not found, add empty component
                CompProps := TStringList.Create;
                try
                    AddJSONProperty(CompProps, 'designator', Designator);
                    CompProps.Add('"pins": []');
                    
                    // Add to components array
                    ComponentsArray.Add(BuildJSONObject(CompProps, 1));
                finally
                    CompProps.Free;
                end;
            end;
        end;
        
        // Build the final JSON array
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONArray(ComponentsArray);
            Result := WriteJSONToFile(OutputLines, ROOT_DIR+'\temp_pins_data.json');
        finally
            OutputLines.Free;
        end;
    finally
        ComponentsArray.Free;
    end;
end;

// Set absolute position of a single component
function SetComponentPosition(Designator: String; NewX, NewY: Float; Rotation: Float): String;
var
    Board: IPCB_Board;
    Component: IPCB_Component;
    ResultProps: TStringList;
    xorigin, yorigin: TCoord;
begin
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := '{"success": false, "error": "No PCB document is currently active"}';
        Exit;
    end;
    
    Component := Board.GetPcbComponentByRefDes(Designator);
    if (Component = nil) then
    begin
        Result := '{"success": false, "error": "Component not found: ' + Designator + '"}';
        Exit;
    end;
    
    // Get board origin
    xorigin := Board.XOrigin;
    yorigin := Board.YOrigin;
    
    ResultProps := TStringList.Create;
    try
        PCBServer.PreProcess;
        PCBServer.SendMessageToRobots(Component.I_ObjectAddress, c_Broadcast, PCBM_BeginModify, c_NoEventData);
        
        // Set absolute position using MoveToXY
        // Add origin back since input coordinates are relative to origin
        Component.MoveToXY(MilsToCoord(NewX) + xorigin, MilsToCoord(NewY) + yorigin);
        
        // Set rotation if specified (use -1 to keep current)
        if (Rotation >= 0) then
            Component.Rotation := Rotation;
        
        PCBServer.SendMessageToRobots(Component.I_ObjectAddress, c_Broadcast, PCBM_EndModify, c_NoEventData);
        PCBServer.PostProcess;
        
        Client.SendMessage('PCB:Zoom', 'Action=Redraw', 255, Client.CurrentView);
        
        AddJSONProperty(ResultProps, 'designator', Designator);
        AddJSONProperty(ResultProps, 'new_x', FloatToStr(NewX), False);
        AddJSONProperty(ResultProps, 'new_y', FloatToStr(NewY), False);
        AddJSONProperty(ResultProps, 'rotation', FloatToStr(Component.Rotation), False);
        
        Result := '{"success": true, "result": ' + BuildJSONObject(ResultProps) + '}';
    finally
        ResultProps.Free;
    end;
end;

// Create a PCB footprint (SMD pads + silkscreen + courtyard) in the active PcbLib
function CreatePCBFootprint(FootprintName: String; Description: String; PadsList: TStringList; CourtyardXMM: Double; CourtyardYMM: Double): String;
var
    PcbLib      : IPCB_Library;
    LibComp     : IPCB_Component;
    Pad         : IPCB_Pad;
    Track       : IPCB_Track;
    ResultProps : TStringList;
    OutputLines : TStringList;
    i, j        : Integer;
    PadData     : String;
    PadNum      : String;
    XMM, YMM    : Double;
    WMM, HMM    : Double;
    ShapeStr    : String;
    PadShape    : TShape;
    PadCount    : Integer;
    MaxX, MaxY  : Double;
    MinX, MinY  : Double;
    CrtX1, CrtY1, CrtX2, CrtY2 : Double;
    TrackWidth  : TCoord;
    FieldStart  : Integer;
    Fields      : TStringList;
    SilkLayer   : TLayer;
begin
    PcbLib := PCBServer.GetCurrentPCBLibrary;
    if PcbLib = nil then
    begin
        Result := '{"success": false, "error": "No PCB library document is currently active. Open a .PcbLib file first."}';
        Exit;
    end;

    ResultProps := TStringList.Create;
    Fields := TStringList.Create;
    PadCount := 0;
    MaxX := -1e9; MaxY := -1e9;
    MinX :=  1e9; MinY :=  1e9;
    SilkLayer := String2Layer('Top Overlay');

    try
        LibComp := PCBServer.CreatePCBLibComp;
        LibComp.Name := FootprintName;

        PcbLib.RegisterComponent(LibComp);

        for i := 0 to PadsList.Count - 1 do
        begin
            PadData := Trim(PadsList[i]);
            if (PadData = '') then continue;

            // Parse pipe-delimited fields manually
            Fields.Clear;
            FieldStart := 1;
            for j := 1 to Length(PadData) + 1 do
            begin
                if (j > Length(PadData)) or (PadData[j] = '|') then
                begin
                    Fields.Add(Trim(Copy(PadData, FieldStart, j - FieldStart)));
                    FieldStart := j + 1;
                end;
            end;

            if Fields.Count < 5 then continue;

            PadNum := Fields[0];
            XMM := SafeStrToFloat(Fields[1]);
            YMM := SafeStrToFloat(Fields[2]);
            WMM := SafeStrToFloat(Fields[3]);
            HMM := SafeStrToFloat(Fields[4]);

            if Fields.Count >= 6 then
                ShapeStr := Fields[5]
            else
                ShapeStr := 'Rect';

            if ShapeStr = 'Round' then
                PadShape := eRounded
            else if ShapeStr = 'Oval' then
                PadShape := eRoundedRectangle
            else
                PadShape := eRectangular;

            Pad := PCBServer.PCBObjectFactory(ePadObject, eNoDimension, eCreate_Default);
            Pad.Name := PadNum;
            Pad.Mode := ePadMode_Simple;
            Pad.HoleSize := 0;
            Pad.x := MMsToCoord(XMM);
            Pad.y := MMsToCoord(YMM);
            Pad.Layer := eTopLayer;
            Pad.TopXSize := MMsToCoord(WMM);
            Pad.TopYSize := MMsToCoord(HMM);
            Pad.TopShape := PadShape;

            LibComp.AddPCBObject(Pad);
            PCBServer.SendMessageToRobots(Pad.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

            if (XMM - WMM/2) < MinX then MinX := XMM - WMM/2;
            if (YMM - HMM/2) < MinY then MinY := YMM - HMM/2;
            if (XMM + WMM/2) > MaxX then MaxX := XMM + WMM/2;
            if (YMM + HMM/2) > MaxY then MaxY := YMM + HMM/2;

            PadCount := PadCount + 1;
        end;

        // Compute courtyard extents
        if (CourtyardXMM > 0) and (CourtyardYMM > 0) then
        begin
            CrtX1 := -CourtyardXMM; CrtX2 :=  CourtyardXMM;
            CrtY1 := -CourtyardYMM; CrtY2 :=  CourtyardYMM;
        end
        else
        begin
            CrtX1 := MinX - 0.25; CrtX2 := MaxX + 0.25;
            CrtY1 := MinY - 0.25; CrtY2 := MaxY + 0.25;
        end;

        TrackWidth := MMsToCoord(0.1);

        // Courtyard on Mechanical 15
        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        Track.Layer := ILayer.MechanicalLayer(15);
        Track.x1 := MMsToCoord(CrtX1); Track.y1 := MMsToCoord(CrtY1);
        Track.x2 := MMsToCoord(CrtX2); Track.y2 := MMsToCoord(CrtY1);
        Track.Width := TrackWidth;
        LibComp.AddPCBObject(Track);
        PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        Track.Layer := ILayer.MechanicalLayer(15);
        Track.x1 := MMsToCoord(CrtX1); Track.y1 := MMsToCoord(CrtY2);
        Track.x2 := MMsToCoord(CrtX2); Track.y2 := MMsToCoord(CrtY2);
        Track.Width := TrackWidth;
        LibComp.AddPCBObject(Track);
        PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        Track.Layer := ILayer.MechanicalLayer(15);
        Track.x1 := MMsToCoord(CrtX1); Track.y1 := MMsToCoord(CrtY1);
        Track.x2 := MMsToCoord(CrtX1); Track.y2 := MMsToCoord(CrtY2);
        Track.Width := TrackWidth;
        LibComp.AddPCBObject(Track);
        PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        Track.Layer := ILayer.MechanicalLayer(15);
        Track.x1 := MMsToCoord(CrtX2); Track.y1 := MMsToCoord(CrtY1);
        Track.x2 := MMsToCoord(CrtX2); Track.y2 := MMsToCoord(CrtY2);
        Track.Width := TrackWidth;
        LibComp.AddPCBObject(Track);
        PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

        // Silkscreen on TopOverlay (inset 0.1mm from courtyard)
        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        Track.Layer := SilkLayer;
        Track.x1 := MMsToCoord(CrtX1+0.1); Track.y1 := MMsToCoord(CrtY1+0.1);
        Track.x2 := MMsToCoord(CrtX2-0.1); Track.y2 := MMsToCoord(CrtY1+0.1);
        Track.Width := TrackWidth;
        LibComp.AddPCBObject(Track);
        PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        Track.Layer := SilkLayer;
        Track.x1 := MMsToCoord(CrtX1+0.1); Track.y1 := MMsToCoord(CrtY2-0.1);
        Track.x2 := MMsToCoord(CrtX2-0.1); Track.y2 := MMsToCoord(CrtY2-0.1);
        Track.Width := TrackWidth;
        LibComp.AddPCBObject(Track);
        PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

        // Left silk — split to mark pin 1 (gap at top-left corner for pin 1 indicator)
        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        Track.Layer := SilkLayer;
        Track.x1 := MMsToCoord(CrtX1+0.1); Track.y1 := MMsToCoord(CrtY1+0.1);
        Track.x2 := MMsToCoord(CrtX1+0.1); Track.y2 := MMsToCoord(CrtY2-0.6);
        Track.Width := TrackWidth;
        LibComp.AddPCBObject(Track);
        PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

        // Right silk
        Track := PCBServer.PCBObjectFactory(eTrackObject, eNoDimension, eCreate_Default);
        Track.Layer := SilkLayer;
        Track.x1 := MMsToCoord(CrtX2-0.1); Track.y1 := MMsToCoord(CrtY1+0.1);
        Track.x2 := MMsToCoord(CrtX2-0.1); Track.y2 := MMsToCoord(CrtY2-0.1);
        Track.Width := TrackWidth;
        LibComp.AddPCBObject(Track);
        PCBServer.SendMessageToRobots(Track.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, c_NoEventData);

        // Register with library board, navigate, and refresh
        PCBServer.SendMessageToRobots(PcbLib.Board.I_ObjectAddress, c_Broadcast, PCBM_BoardRegisteration, LibComp.I_ObjectAddress);
        PcbLib.CurrentComponent := LibComp;
        PcbLib.Board.ViewManager_FullUpdate;

        AddJSONBoolean(ResultProps, 'success', True);
        AddJSONProperty(ResultProps, 'footprint_name', FootprintName);
        AddJSONInteger(ResultProps, 'pad_count', PadCount);
        AddJSONNumber(ResultProps, 'courtyard_width_mm', CrtX2 - CrtX1);
        AddJSONNumber(ResultProps, 'courtyard_height_mm', CrtY2 - CrtY1);

        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
        Fields.Free;
    end;
end;

// Function to move components by X and Y offsets and set rotation
function MoveComponentsByDesignators(DesignatorsList: TStringList; XOffset, YOffset: TCoord; Rotation: TAngle): String;
var
    Board          : IPCB_Board;
    Component      : IPCB_Component;
    ResultProps    : TStringList;
    MissingArray   : TStringList;
    Designator     : String;
    i              : Integer;
    MovedCount     : Integer;
    OutputLines    : TStringList;
begin
    // Retrieve the current board
    Board := PCBServer.GetCurrentPCBBoard;
    if (Board = nil) then
    begin
        Result := 'ERROR: No PCB document is currently active';
        Exit;
    end;
    
    // Create output properties
    ResultProps := TStringList.Create;
    MissingArray := TStringList.Create;
    MovedCount := 0;
    
    try
        // Start transaction
        PCBServer.PreProcess;
        
        // Process each designator
        for i := 0 to DesignatorsList.Count - 1 do
        begin
            Designator := Trim(DesignatorsList[i]);
            
            // Use direct function to get component by designator
            Component := Board.GetPcbComponentByRefDes(Designator);
            
            if (Component <> Nil) then
            begin
                // Begin modify
                PCBServer.SendMessageToRobots(Component.I_ObjectAddress, c_Broadcast, PCBM_BeginModify, c_NoEventData);
                
                // Move the component by the specified offsets
                Component.MoveByXY(XOffset, YOffset);
                
                // Set rotation if specified (non-zero)
                if (Rotation <> 0) then
                    Component.Rotation := Rotation;
                
                // End modify
                PCBServer.SendMessageToRobots(Component.I_ObjectAddress, c_Broadcast, PCBM_EndModify, c_NoEventData);
                
                MovedCount := MovedCount + 1;
            end
            else
            begin
                // Add to missing designators list
                MissingArray.Add('"' + JSONEscapeString(Designator) + '"');
            end;
        end;
        
        // End transaction
        PCBServer.PostProcess;
        
        // Update PCB document
        Client.SendMessage('PCB:Zoom', 'Action=Redraw', 255, Client.CurrentView);
        
        // Create result JSON
        AddJSONInteger(ResultProps, 'moved_count', MovedCount);
        
        // Add missing designators array
        if (MissingArray.Count > 0) then
            ResultProps.Add(BuildJSONArray(MissingArray, 'missing_designators'))
        else
            ResultProps.Add('"missing_designators": []');
        
        // Build final JSON
        OutputLines := TStringList.Create;
        try
            OutputLines.Text := BuildJSONObject(ResultProps);
            Result := OutputLines.Text;
        finally
            OutputLines.Free;
        end;
    finally
        ResultProps.Free;
        MissingArray.Free;
    end;
end;
