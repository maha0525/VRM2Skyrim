Scriptname V2SInitialWardrobe extends Actor

FormList Property InitialItems Auto
FormList Property BodyClothes Auto
FormList Property HandsClothes Auto
FormList Property FeetClothes Auto
FormList Property BodyEquipment Auto
FormList Property HandsEquipment Auto
FormList Property FeetEquipment Auto

Bool initialized = False

Event OnInit()
    If initialized
        Return
    EndIf
    initialized = True
    ; Added scripts on an existing follower must not replace their chosen gear.
    If IsPlayerTeammate()
        ResolveCurrentEquipment()
        Debug.Trace("VRM2Skyrim: initial wardrobe skipped for existing teammate")
        Return
    EndIf
    Int i = 0
    While i < InitialItems.GetSize()
        Form item = InitialItems.GetAt(i)
        If item && GetItemCount(item) > 0
            EquipItem(item, False, True)
        EndIf
        i += 1
    EndWhile
    Debug.Trace("VRM2Skyrim: initial wardrobe equipped once")
EndEvent

Bool Function AnyEquipped(FormList items)
    Int i = 0
    While i < items.GetSize()
        If IsEquipped(items.GetAt(i))
            Return True
        EndIf
        i += 1
    EndWhile
    Return False
EndFunction

Function ResolveCurrentEquipment()
    If AnyEquipped(BodyEquipment)
        UnequipConflicts(BodyClothes)
    EndIf
    If AnyEquipped(HandsEquipment)
        UnequipConflicts(HandsClothes)
    EndIf
    If AnyEquipped(FeetEquipment)
        UnequipConflicts(FeetClothes)
    EndIf
EndFunction

Event OnLoad()
    ; Repair an existing overlap; never restore items or a default outfit.
    ResolveCurrentEquipment()
EndEvent

Function UnequipConflicts(FormList items)
    Int i = 0
    While i < items.GetSize()
        Form item = items.GetAt(i)
        If item && IsEquipped(item)
            UnequipItem(item, False, True)
            Debug.Trace("VRM2Skyrim: unequipped conflicting garment/equipment " + item)
        EndIf
        i += 1
    EndWhile
EndFunction

Event OnObjectEquipped(Form akBaseObject, ObjectReference akReference)
    ; Ignore delayed events for equipment another handler has already removed.
    If !IsEquipped(akBaseObject)
        Return
    EndIf
    If BodyEquipment.HasForm(akBaseObject)
        UnequipConflicts(BodyClothes)
    ElseIf HandsEquipment.HasForm(akBaseObject)
        UnequipConflicts(HandsClothes)
    ElseIf FeetEquipment.HasForm(akBaseObject)
        UnequipConflicts(FeetClothes)
    ElseIf BodyClothes.HasForm(akBaseObject)
        UnequipConflicts(BodyEquipment)
    ElseIf HandsClothes.HasForm(akBaseObject)
        UnequipConflicts(HandsEquipment)
    ElseIf FeetClothes.HasForm(akBaseObject)
        UnequipConflicts(FeetEquipment)
    EndIf
EndEvent
