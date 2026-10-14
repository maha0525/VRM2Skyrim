Scriptname V2SSeating extends Actor

FormList Property Seats Auto
Float Property Offset Auto

Bool applied = False
Float baseline = 0.0
Float expected = 0.0
Int entryRetries = 0

Function ClearCorrection()
    If applied && Is3DLoaded() && NetImmerse.HasNode(Self, "NPC", False)
        Float current = NetImmerse.GetNodeLocalPositionZ(Self, "NPC", False)
        ; Never restore a stale value after a rebuild or another adjustment.
        If current == expected
            NetImmerse.SetNodeLocalPositionZ(Self, "NPC", baseline, False)
            Debug.Trace("VRM2Skyrim: seated height cleared")
        EndIf
    EndIf
    applied = False
EndFunction

Function RegisterChairEvents()
    ; Names read from Skyrim's 0_master behavior and time-zero annotations in
    ; the male/female front/left/right chair-entry clips. No behavior edits.
    Bool registered = RegisterForAnimationEvent(Self, "IdleFurnitureStart")
    registered = RegisterForAnimationEvent(Self, "IdleChairEnterStart") || registered
    registered = RegisterForAnimationEvent(Self, "IdleLeftChairEnterStart") || registered
    registered = RegisterForAnimationEvent(Self, "IdleRightChairEnterStart") || registered
    registered = RegisterForAnimationEvent(Self, "SoundPlay.NPCHumanSitChairDown") || registered
    registered = RegisterForAnimationEvent(Self, "SoundPlay.NPCHumanSitChairDownLR") || registered
    If !registered && Is3DLoaded()
        Debug.Trace("VRM2Skyrim: chair-entry events unavailable; OnSit fallback remains active")
    EndIf
EndFunction

Function RefreshSeating()
    If !Is3DLoaded()
        entryRetries = 0
        Return
    EndIf
    Bool seated = False
    Int sitState = GetSitState()
    ; Animation notification and native sit state are not synchronized. Retry
    ; at 0.1-second intervals, at most 40 times, instead of a single-frame retry.
    If sitState == 0 && entryRetries > 0
        entryRetries = entryRetries + -1
        ClearCorrection()
        RegisterForSingleUpdate(0.1)
        Return
    EndIf
    entryRetries = 0
    If (sitState == 2 || sitState == 3) && GetSleepState() == 0 && !IsOnMount()
        ObjectReference furniture = GetFurnitureReference()
        If furniture && Seats.HasForm(furniture.GetBaseObject())
            seated = True
        EndIf
    EndIf
    If NetImmerse.HasNode(Self, "NPC", False)
        If seated && Offset != 0.0
            Float current = NetImmerse.GetNodeLocalPositionZ(Self, "NPC", False)
            If !applied
                baseline = current
                expected = baseline + Offset
                ; Publish ownership before this native call can yield to a
                ; second event; otherwise that event could add Offset again.
                applied = True
                NetImmerse.SetNodeLocalPositionZ(Self, "NPC", expected, False)
                Debug.Trace("VRM2Skyrim: chair height=" + Offset + "; sitState=" + sitState)
            ElseIf current == baseline
                ; Recover a reset node without adding the offset twice.
                NetImmerse.SetNodeLocalPositionZ(Self, "NPC", expected, False)
            EndIf
        Else
            ClearCorrection()
        EndIf
    EndIf
    ; Reconcile delayed exit events and rebuilt 3D only during furniture use.
    If sitState == 2 || sitState == 3 || sitState == 4
        RegisterForSingleUpdate(0.5)
    EndIf
EndFunction

Event OnInit()
    RegisterForNiNodeUpdate()
    RegisterChairEvents()
    RefreshSeating()
EndEvent

Event OnLoad()
    entryRetries = 0
    ClearCorrection()
    RegisterForNiNodeUpdate()
    RegisterChairEvents()
    RefreshSeating()
EndEvent

Event OnSit(ObjectReference akFurniture)
    RefreshSeating()
EndEvent

Event OnGetUp(ObjectReference akFurniture)
    RefreshSeating()
EndEvent

Event OnUpdate()
    RefreshSeating()
EndEvent

Event OnAnimationEvent(ObjectReference akSource, String asEventName)
    If akSource == Self
        If asEventName == "IdleFurnitureStart" || asEventName == "IdleChairEnterStart" || asEventName == "IdleLeftChairEnterStart" || asEventName == "IdleRightChairEnterStart" || asEventName == "SoundPlay.NPCHumanSitChairDown" || asEventName == "SoundPlay.NPCHumanSitChairDownLR"
            ; Event may precede state 2. Never shift a standing actor solely
            ; from a notification; use a bounded retry window for state visibility.
            If GetSitState() == 0
                entryRetries = 40
            EndIf
            Debug.Trace("VRM2Skyrim: chair-entry event=" + asEventName)
            RefreshSeating()
        EndIf
    EndIf
EndEvent

Event OnNiNodeUpdate(ObjectReference akActor)
    If akActor == Self
        RegisterChairEvents()
        If applied && Is3DLoaded() && NetImmerse.HasNode(Self, "NPC", False)
            If NetImmerse.GetNodeLocalPositionZ(Self, "NPC", False) != expected
                applied = False
            EndIf
        EndIf
        RefreshSeating()
    EndIf
EndEvent

Event OnUnload()
    entryRetries = 0
    UnregisterForUpdate()
    ClearCorrection()
EndEvent
