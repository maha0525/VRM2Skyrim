Scriptname V2SSeating extends Actor

FormList Property Seats Auto
Float Property Offset Auto

Bool applied = False
Float baseline = 0.0
Float expected = 0.0

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

Function RefreshSeating()
    If !Is3DLoaded()
        Return
    EndIf
    Bool seated = False
    Int sitState = GetSitState()
    If sitState == 3 && GetSleepState() == 0 && !IsOnMount()
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
                NetImmerse.SetNodeLocalPositionZ(Self, "NPC", expected, False)
                applied = True
                Debug.Trace("VRM2Skyrim: seated height=" + Offset)
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
    RefreshSeating()
EndEvent

Event OnLoad()
    ClearCorrection()
    RegisterForNiNodeUpdate()
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

Event OnNiNodeUpdate(ObjectReference akActor)
    If akActor == Self
        If applied && Is3DLoaded() && NetImmerse.HasNode(Self, "NPC", False)
            If NetImmerse.GetNodeLocalPositionZ(Self, "NPC", False) != expected
                applied = False
            EndIf
        EndIf
        RefreshSeating()
    EndIf
EndEvent

Event OnUnload()
    UnregisterForUpdate()
    ClearCorrection()
EndEvent
