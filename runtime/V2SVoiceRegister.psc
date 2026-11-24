Scriptname V2SVoiceRegister extends Quest

FormList Property VoicesFollowerAll Auto
FormList Property DefaultNPCVoiceTypes Auto
VoiceType Property CustomVoice Auto

Event OnInit()
    RegisterVoice()
EndEvent

Function RegisterVoice()
    If CustomVoice == None
        Return
    EndIf
    If VoicesFollowerAll && !VoicesFollowerAll.HasForm(CustomVoice)
        VoicesFollowerAll.AddForm(CustomVoice)
    EndIf
    ; Ensure custom voice is NOT in DefaultNPCVoiceTypes so vanilla DialogueGeneric unvoiced lines never trigger
    If DefaultNPCVoiceTypes && DefaultNPCVoiceTypes.HasForm(CustomVoice)
        DefaultNPCVoiceTypes.RemoveAddedForm(CustomVoice)
    EndIf
    Debug.Trace("VRM2Skyrim: registered custom voice " + CustomVoice)
EndFunction
