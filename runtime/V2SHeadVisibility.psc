Scriptname V2SHeadVisibility extends Actor

Armor Property FullSkin Auto
Armor Property FaceHiddenSkin Auto
Armor Property HairHiddenSkin Auto
Armor Property BothHiddenSkin Auto
FormList Property FaceHidingEquipment Auto
FormList Property HairHidingEquipment Auto

Bool Function AnyEquipped(FormList items)
    Int i = 0
    Int mask = 1
    ; Scan worn layers instead of thousands of enchanted inventory definitions.
    While i < 32
        Form worn = GetWornForm(mask)
        If worn && items.HasForm(worn)
            Return True
        EndIf
        i += 1
        mask *= 2
    EndWhile
    Return False
EndFunction

Function RefreshVisibility()
    Bool face = AnyEquipped(FaceHidingEquipment)
    Bool hair = AnyEquipped(HairHidingEquipment)
    Armor desired = FullSkin
    If face && hair
        desired = BothHiddenSkin
    ElseIf face
        desired = FaceHiddenSkin
    ElseIf hair
        desired = HairHiddenSkin
    EndIf
    ActorBase base = GetActorBase()
    If base && base.GetSkin() != desired
        base.SetSkin(desired)
        QueueNiNodeUpdate()
        Debug.Trace("VRM2Skyrim: head visibility skin=" + desired)
    EndIf
EndFunction

Event OnInit()
    RegisterForNiNodeUpdate()
    RefreshVisibility()
EndEvent

Event OnLoad()
    RegisterForNiNodeUpdate()
    RefreshVisibility()
EndEvent

Event OnObjectEquipped(Form akBaseObject, ObjectReference akReference)
    RefreshVisibility()
EndEvent

Event OnObjectUnequipped(Form akBaseObject, ObjectReference akReference)
    RefreshVisibility()
EndEvent

Event OnNiNodeUpdate(ObjectReference akActor)
    If akActor == Self
        RefreshVisibility()
    EndIf
EndEvent
