.info
  .source "C:\\Users\\shuhe\\workspace\\games\\vrm-skyrim-converter\\runtime\\V2SSeating.psc"
  .modifyTime 0
  .compileTime 1792003349
  .user "shuhe"
  .computer "SAIV-EARTH"
.endInfo
.userFlagsRef
.endUserFlagsRef
.objectTable
  .object V2SSeating Actor
    .userFlags 0
    .docString ""
    .autoState
    .structTable
    .endStructTable
    .variableTable
      .variable applied Bool
        .userFlags 0
        .initialValue False
      .endVariable
      .variable baseline Float
        .userFlags 0
        .initialValue 0.000000
      .endVariable
      .variable expected Float
        .userFlags 0
        .initialValue 0.000000
      .endVariable
      .variable entryRetries Int
        .userFlags 0
        .initialValue 0
      .endVariable
      .variable ::Seats_var formList
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::Offset_var Float
        .userFlags 0
        .initialValue None
      .endVariable
    .endVariableTable
    .guardTable
    .endGuardTable
    .propertyTable
      .property Seats formList auto
        .userFlags 0
        .docString ""
        .autoVar ::Seats_var
      .endProperty
      .property Offset Float auto
        .userFlags 0
        .docString ""
        .autoVar ::Offset_var
      .endProperty
    .endPropertyTable
    .propertyGroupTable
    .endPropertyGroupTable
    .stateTable
      .state
        .function GetState
          .userFlags 0
          .docString "Function that returns the current state"
          .return String
          .paramTable
          .endParamTable
          .localTable
          .endLocalTable
          .code
            RETURN ::State
          .endCode
        .endFunction
        .function GotoState
          .userFlags 0
          .docString "Function that switches this object to the specified state"
          .return None
          .paramTable
            .param newState String
          .endParamTable
          .localTable
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD onEndState self ::nonevar
            ASSIGN ::State newState
            CALLMETHOD onBeginState self ::nonevar
          .endCode
        .endFunction
        .function OnNiNodeUpdate
          .userFlags 0
          .docString ""
          .return None
          .paramTable
            .param akActor objectReference
          .endParamTable
          .localTable
            .local ::temp0 objectReference
            .local ::temp1 Bool
            .local ::nonevar None
            .local ::temp2 Float
          .endLocalTable
          .code
            CAST ::temp0 self ;@line 125
            COMPAREEQ ::temp1 akActor ::temp0 ;@line 125
            JUMPF ::temp1 label0 ;@line 125
            CALLMETHOD RegisterChairEvents self ::nonevar ;@line 126
            ASSIGN ::temp1 applied ;@line 127
            JUMPF ::temp1 label1 ;@line 127
            CALLMETHOD Is3DLoaded self ::temp1 ;@line 127
            ASSIGN ::temp1 ::temp1 ;@line 127
            label1:
            ASSIGN ::temp1 ::temp1 ;@line 127
            JUMPF ::temp1 label2 ;@line 127
            CAST ::temp0 self ;@line 127
            CALLSTATIC netImmerse HasNode ::temp1 ::temp0 "NPC" False ;@line 127
            ASSIGN ::temp1 ::temp1 ;@line 127
            label2:
            JUMPF ::temp1 label3 ;@line 127
            CAST ::temp0 self ;@line 128
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp2 ::temp0 "NPC" False ;@line 128
            COMPAREEQ ::temp1 ::temp2 expected ;@line 128
            NOT ::temp1 ::temp1 ;@line 128
            JUMPF ::temp1 label4 ;@line 128
            ASSIGN applied False ;@line 129
            JUMP label4 ;@line 129
            label4:
            JUMP label3 ;@line 129
            label3:
            CALLMETHOD RefreshSeating self ::nonevar ;@line 132
            JUMP label0 ;@line 132
            label0:
          .endCode
        .endFunction
        .function OnGetUp
          .userFlags 0
          .docString ""
          .return None
          .paramTable
            .param akFurniture objectReference
          .endParamTable
          .localTable
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD RefreshSeating self ::nonevar ;@line 103
          .endCode
        .endFunction
        .function ClearCorrection
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local ::temp0 Bool
            .local ::temp1 objectReference
            .local current Float
            .local ::temp2 Float
            .local ::nonevar None
          .endLocalTable
          .code
            ASSIGN ::temp0 applied ;@line 12
            JUMPF ::temp0 label0 ;@line 12
            CALLMETHOD Is3DLoaded self ::temp0 ;@line 12
            ASSIGN ::temp0 ::temp0 ;@line 12
            label0:
            ASSIGN ::temp0 ::temp0 ;@line 12
            JUMPF ::temp0 label1 ;@line 12
            CAST ::temp1 self ;@line 12
            CALLSTATIC netImmerse HasNode ::temp0 ::temp1 "NPC" False ;@line 12
            ASSIGN ::temp0 ::temp0 ;@line 12
            label1:
            JUMPF ::temp0 label2 ;@line 12
            CAST ::temp1 self ;@line 13
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp2 ::temp1 "NPC" False ;@line 13
            ASSIGN current ::temp2 ;@line 13
            COMPAREEQ ::temp0 current expected ;@line 15
            JUMPF ::temp0 label3 ;@line 15
            CAST ::temp1 self ;@line 16
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp1 "NPC" baseline False ;@line 16
            CALLSTATIC debug Trace ::nonevar "VRM2Skyrim: seated height cleared" 0 ;@line 17
            JUMP label3 ;@line 17
            label3:
            JUMP label2 ;@line 17
            label2:
            ASSIGN applied False ;@line 20
          .endCode
        .endFunction
        .function OnSit
          .userFlags 0
          .docString ""
          .return None
          .paramTable
            .param akFurniture objectReference
          .endParamTable
          .localTable
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD RefreshSeating self ::nonevar ;@line 99
          .endCode
        .endFunction
        .function RegisterChairEvents
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local registered Bool
            .local ::temp0 objectReference
            .local ::temp1 Bool
            .local ::nonevar None
          .endLocalTable
          .code
            CAST ::temp0 self ;@line 26
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "IdleFurnitureStart" ;@line 26
            ASSIGN registered ::temp1 ;@line 26
            CAST ::temp0 self ;@line 27
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "IdleChairEnterStart" ;@line 27
            ASSIGN ::temp1 ::temp1 ;@line 27
            JUMPT ::temp1 label0 ;@line 27
            ASSIGN ::temp1 registered ;@line 27
            label0:
            ASSIGN registered ::temp1 ;@line 27
            CAST ::temp0 self ;@line 28
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "IdleLeftChairEnterStart" ;@line 28
            ASSIGN ::temp1 ::temp1 ;@line 28
            JUMPT ::temp1 label1 ;@line 28
            ASSIGN ::temp1 registered ;@line 28
            label1:
            ASSIGN registered ::temp1 ;@line 28
            CAST ::temp0 self ;@line 29
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "IdleRightChairEnterStart" ;@line 29
            ASSIGN ::temp1 ::temp1 ;@line 29
            JUMPT ::temp1 label2 ;@line 29
            ASSIGN ::temp1 registered ;@line 29
            label2:
            ASSIGN registered ::temp1 ;@line 29
            CAST ::temp0 self ;@line 30
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "SoundPlay.NPCHumanSitChairDown" ;@line 30
            ASSIGN ::temp1 ::temp1 ;@line 30
            JUMPT ::temp1 label3 ;@line 30
            ASSIGN ::temp1 registered ;@line 30
            label3:
            ASSIGN registered ::temp1 ;@line 30
            CAST ::temp0 self ;@line 31
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "SoundPlay.NPCHumanSitChairDownLR" ;@line 31
            ASSIGN ::temp1 ::temp1 ;@line 31
            JUMPT ::temp1 label4 ;@line 31
            ASSIGN ::temp1 registered ;@line 31
            label4:
            ASSIGN registered ::temp1 ;@line 31
            NOT ::temp1 registered ;@line 32
            ASSIGN ::temp1 ::temp1 ;@line 32
            JUMPF ::temp1 label5 ;@line 32
            CALLMETHOD Is3DLoaded self ::temp1 ;@line 32
            ASSIGN ::temp1 ::temp1 ;@line 32
            label5:
            JUMPF ::temp1 label6 ;@line 32
            CALLSTATIC debug Trace ::nonevar "VRM2Skyrim: chair-entry events unavailable; OnSit fallback remains active" 0 ;@line 33
            JUMP label6 ;@line 33
            label6:
          .endCode
        .endFunction
        .function OnUpdate
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD RefreshSeating self ::nonevar ;@line 107
          .endCode
        .endFunction
        .function OnInit
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 85
            CALLMETHOD RegisterChairEvents self ::nonevar ;@line 86
            CALLMETHOD RefreshSeating self ::nonevar ;@line 87
          .endCode
        .endFunction
        .function RefreshSeating
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local ::temp0 Bool
            .local seated Bool
            .local sitState Int
            .local ::temp1 Int
            .local ::nonevar None
            .local furniture objectReference
            .local ::temp2 objectReference
            .local ::temp3 form
            .local current Float
            .local ::temp4 Float
            .local ::temp5 String
            .local ::temp6 String
          .endLocalTable
          .code
            CALLMETHOD Is3DLoaded self ::temp0 ;@line 38
            NOT ::temp0 ::temp0 ;@line 38
            JUMPF ::temp0 label0 ;@line 38
            ASSIGN entryRetries 0 ;@line 39
            RETURN None ;@line 40
            JUMP label0 ;@line 40
            label0:
            ASSIGN seated False ;@line 42
            CALLMETHOD GetSitState self ::temp1 ;@line 43
            ASSIGN sitState ::temp1 ;@line 43
            COMPAREEQ ::temp0 sitState 0 ;@line 46
            ASSIGN ::temp0 ::temp0 ;@line 46
            JUMPF ::temp0 label1 ;@line 46
            COMPAREGT ::temp0 entryRetries 0 ;@line 46
            ASSIGN ::temp0 ::temp0 ;@line 46
            label1:
            JUMPF ::temp0 label2 ;@line 46
            IADD ::temp1 entryRetries -1 ;@line 47
            ASSIGN entryRetries ::temp1 ;@line 47
            CALLMETHOD ClearCorrection self ::nonevar ;@line 48
            CALLMETHOD RegisterForSingleUpdate self ::nonevar 0.100000 ;@line 49
            RETURN None ;@line 50
            JUMP label2 ;@line 50
            label2:
            ASSIGN entryRetries 0 ;@line 52
            COMPAREEQ ::temp0 sitState 2 ;@line 53
            ASSIGN ::temp0 ::temp0 ;@line 53
            JUMPT ::temp0 label3 ;@line 53
            COMPAREEQ ::temp0 sitState 3 ;@line 53
            ASSIGN ::temp0 ::temp0 ;@line 53
            label3:
            ASSIGN ::temp0 ::temp0 ;@line 53
            JUMPF ::temp0 label4 ;@line 53
            CALLMETHOD GetSleepState self ::temp1 ;@line 53
            COMPAREEQ ::temp0 ::temp1 0 ;@line 53
            ASSIGN ::temp0 ::temp0 ;@line 53
            label4:
            ASSIGN ::temp0 ::temp0 ;@line 53
            JUMPF ::temp0 label5 ;@line 53
            CALLMETHOD IsOnMount self ::temp0 ;@line 53
            NOT ::temp0 ::temp0 ;@line 53
            ASSIGN ::temp0 ::temp0 ;@line 53
            label5:
            JUMPF ::temp0 label6 ;@line 53
            CALLMETHOD GetFurnitureReference self ::temp2 ;@line 54
            ASSIGN furniture ::temp2 ;@line 54
            CAST ::temp0 furniture ;@line 55
            ASSIGN ::temp0 ::temp0 ;@line 55
            JUMPF ::temp0 label7 ;@line 55
            CALLMETHOD GetBaseObject furniture ::temp3 ;@line 55
            CALLMETHOD HasForm ::Seats_var ::temp0 ::temp3 ;@line 55
            ASSIGN ::temp0 ::temp0 ;@line 55
            label7:
            JUMPF ::temp0 label8 ;@line 55
            ASSIGN seated True ;@line 56
            JUMP label8 ;@line 56
            label8:
            JUMP label6 ;@line 56
            label6:
            CAST ::temp2 self ;@line 59
            CALLSTATIC netImmerse HasNode ::temp0 ::temp2 "NPC" False ;@line 59
            JUMPF ::temp0 label9 ;@line 59
            ASSIGN ::temp0 seated ;@line 60
            JUMPF ::temp0 label10 ;@line 60
            COMPAREEQ ::temp0 ::Offset_var 0.000000 ;@line 60
            NOT ::temp0 ::temp0 ;@line 60
            ASSIGN ::temp0 ::temp0 ;@line 60
            label10:
            JUMPF ::temp0 label11 ;@line 60
            CAST ::temp2 self ;@line 61
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp4 ::temp2 "NPC" False ;@line 61
            ASSIGN current ::temp4 ;@line 61
            NOT ::temp0 applied ;@line 62
            JUMPF ::temp0 label12 ;@line 62
            ASSIGN baseline current ;@line 63
            FADD ::temp4 baseline ::Offset_var ;@line 64
            ASSIGN expected ::temp4 ;@line 64
            ASSIGN applied True ;@line 67
            CAST ::temp2 self ;@line 68
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp2 "NPC" expected False ;@line 68
            CAST ::temp5 ::Offset_var ;@line 69
            STRCAT ::temp5 "VRM2Skyrim: chair height=" ::temp5 ;@line 69
            STRCAT ::temp5 ::temp5 "; sitState=" ;@line 69
            CAST ::temp6 sitState ;@line 69
            STRCAT ::temp6 ::temp5 ::temp6 ;@line 69
            CALLSTATIC debug Trace ::nonevar ::temp6 0 ;@line 69
            JUMP label13 ;@line 69
            label12:
            COMPAREEQ ::temp0 current baseline ;@line 70
            JUMPF ::temp0 label13 ;@line 70
            CAST ::temp2 self ;@line 72
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp2 "NPC" expected False ;@line 72
            JUMP label13 ;@line 72
            label13:
            JUMP label14 ;@line 72
            label11:
            CALLMETHOD ClearCorrection self ::nonevar ;@line 75
            label14:
            JUMP label9 ;@line 75
            label9:
            COMPAREEQ ::temp0 sitState 2 ;@line 79
            ASSIGN ::temp0 ::temp0 ;@line 79
            JUMPT ::temp0 label15 ;@line 79
            COMPAREEQ ::temp0 sitState 3 ;@line 79
            ASSIGN ::temp0 ::temp0 ;@line 79
            label15:
            ASSIGN ::temp0 ::temp0 ;@line 79
            JUMPT ::temp0 label16 ;@line 79
            COMPAREEQ ::temp0 sitState 4 ;@line 79
            ASSIGN ::temp0 ::temp0 ;@line 79
            label16:
            JUMPF ::temp0 label17 ;@line 79
            CALLMETHOD RegisterForSingleUpdate self ::nonevar 0.500000 ;@line 80
            JUMP label17 ;@line 80
            label17:
          .endCode
        .endFunction
        .function OnLoad
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local ::nonevar None
          .endLocalTable
          .code
            ASSIGN entryRetries 0 ;@line 91
            CALLMETHOD ClearCorrection self ::nonevar ;@line 92
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 93
            CALLMETHOD RegisterChairEvents self ::nonevar ;@line 94
            CALLMETHOD RefreshSeating self ::nonevar ;@line 95
          .endCode
        .endFunction
        .function OnAnimationEvent
          .userFlags 0
          .docString ""
          .return None
          .paramTable
            .param akSource objectReference
            .param asEventName String
          .endParamTable
          .localTable
            .local ::temp0 objectReference
            .local ::temp1 Bool
            .local ::temp2 Int
            .local ::nonevar None
            .local ::temp3 String
          .endLocalTable
          .code
            CAST ::temp0 self ;@line 111
            COMPAREEQ ::temp1 akSource ::temp0 ;@line 111
            JUMPF ::temp1 label0 ;@line 111
            COMPAREEQ ::temp1 asEventName "IdleFurnitureStart" ;@line 112
            ASSIGN ::temp1 ::temp1 ;@line 112
            JUMPT ::temp1 label1 ;@line 112
            COMPAREEQ ::temp1 asEventName "IdleChairEnterStart" ;@line 112
            ASSIGN ::temp1 ::temp1 ;@line 112
            label1:
            ASSIGN ::temp1 ::temp1 ;@line 112
            JUMPT ::temp1 label2 ;@line 112
            COMPAREEQ ::temp1 asEventName "IdleLeftChairEnterStart" ;@line 112
            ASSIGN ::temp1 ::temp1 ;@line 112
            label2:
            ASSIGN ::temp1 ::temp1 ;@line 112
            JUMPT ::temp1 label3 ;@line 112
            COMPAREEQ ::temp1 asEventName "IdleRightChairEnterStart" ;@line 112
            ASSIGN ::temp1 ::temp1 ;@line 112
            label3:
            ASSIGN ::temp1 ::temp1 ;@line 112
            JUMPT ::temp1 label4 ;@line 112
            COMPAREEQ ::temp1 asEventName "SoundPlay.NPCHumanSitChairDown" ;@line 112
            ASSIGN ::temp1 ::temp1 ;@line 112
            label4:
            ASSIGN ::temp1 ::temp1 ;@line 112
            JUMPT ::temp1 label5 ;@line 112
            COMPAREEQ ::temp1 asEventName "SoundPlay.NPCHumanSitChairDownLR" ;@line 112
            ASSIGN ::temp1 ::temp1 ;@line 112
            label5:
            JUMPF ::temp1 label6 ;@line 112
            CALLMETHOD GetSitState self ::temp2 ;@line 115
            COMPAREEQ ::temp1 ::temp2 0 ;@line 115
            JUMPF ::temp1 label7 ;@line 115
            ASSIGN entryRetries 40 ;@line 116
            JUMP label7 ;@line 116
            label7:
            STRCAT ::temp3 "VRM2Skyrim: chair-entry event=" asEventName ;@line 118
            CALLSTATIC debug Trace ::nonevar ::temp3 0 ;@line 118
            CALLMETHOD RefreshSeating self ::nonevar ;@line 119
            JUMP label6 ;@line 119
            label6:
            JUMP label0 ;@line 119
            label0:
          .endCode
        .endFunction
        .function OnUnload
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local ::nonevar None
          .endLocalTable
          .code
            ASSIGN entryRetries 0 ;@line 137
            CALLMETHOD UnregisterForUpdate self ::nonevar ;@line 138
            CALLMETHOD ClearCorrection self ::nonevar ;@line 139
          .endCode
        .endFunction
      .endState
    .endStateTable
  .endObject
.endObjectTable
