Scriptname V2SSeating extends Actor

FormList Property Seats Auto
Float Property Offset Auto

Function RefreshSeating()
    If !Is3DLoaded()
        Return
    EndIf
    Float desired = 0.0
    Int sitState = GetSitState()
    If sitState == 3 && GetSleepState() == 0 && !IsOnMount()
        ObjectReference furniture = GetFurnitureReference()
        If furniture && Seats.HasForm(furniture.GetBaseObject())
            desired = Offset
        EndIf
    EndIf
    If NetImmerse.HasNode(Self, "VRM2SkyrimSeating", False)
        Float current = NetImmerse.GetNodeLocalPositionZ(Self, "VRM2SkyrimSeating", False)
        If current != desired
            NetImmerse.SetNodeLocalPositionZ(Self, "VRM2SkyrimSeating", desired, False)
            Debug.Trace("VRM2Skyrim: seated height=" + desired)
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
        RefreshSeating()
    EndIf
EndEvent

Event OnUnload()
    UnregisterForUpdate()
    If Is3DLoaded() && NetImmerse.HasNode(Self, "VRM2SkyrimSeating", False)
        NetImmerse.SetNodeLocalPositionZ(Self, "VRM2SkyrimSeating", 0.0, False)
    EndIf
EndEvent
