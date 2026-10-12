Scriptname V2SInitialWardrobe extends Actor

FormList Property InitialItems Auto
; Retired bindings kept so old saves can load the replacement script safely.
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
    If IsPlayerTeammate()
        Debug.Trace("VRM2Skyrim: initial equip skipped for existing teammate; native slots own equipment")
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
    Debug.Trace("VRM2Skyrim: initial clothes equipped once; replacement uses native slots")
EndEvent

; Inert legacy entry points: delayed/saved events must never change worn items.
Bool Function AnyEquipped(FormList items, Int slotMask)
    Return False
EndFunction

Function ResolveCurrentEquipment()
EndFunction

Function UnequipConflicts(FormList items)
EndFunction

Event OnLoad()
EndEvent

Event OnObjectEquipped(Form akBaseObject, ObjectReference akReference)
EndEvent
