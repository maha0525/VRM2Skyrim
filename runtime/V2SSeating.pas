.info
  .source "C:\\Users\\shuhe\\workspace\\games\\vrm-skyrim-converter\\runtime\\V2SSeating.psc"
  .modifyTime 0
  .compileTime 1792000874
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
            CAST ::temp0 self ;@line 111
            COMPAREEQ ::temp1 akActor ::temp0 ;@line 111
            JUMPF ::temp1 label0 ;@line 111
            CALLMETHOD RegisterChairEvents self ::nonevar ;@line 112
            ASSIGN ::temp1 applied ;@line 113
            JUMPF ::temp1 label1 ;@line 113
            CALLMETHOD Is3DLoaded self ::temp1 ;@line 113
            ASSIGN ::temp1 ::temp1 ;@line 113
            label1:
            ASSIGN ::temp1 ::temp1 ;@line 113
            JUMPF ::temp1 label2 ;@line 113
            CAST ::temp0 self ;@line 113
            CALLSTATIC netImmerse HasNode ::temp1 ::temp0 "NPC" False ;@line 113
            ASSIGN ::temp1 ::temp1 ;@line 113
            label2:
            JUMPF ::temp1 label3 ;@line 113
            CAST ::temp0 self ;@line 114
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp2 ::temp0 "NPC" False ;@line 114
            COMPAREEQ ::temp1 ::temp2 expected ;@line 114
            NOT ::temp1 ::temp1 ;@line 114
            JUMPF ::temp1 label4 ;@line 114
            ASSIGN applied False ;@line 115
            JUMP label4 ;@line 115
            label4:
            JUMP label3 ;@line 115
            label3:
            CALLMETHOD RefreshSeating self ::nonevar ;@line 118
            JUMP label0 ;@line 118
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 89
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
            ASSIGN ::temp0 applied ;@line 11
            JUMPF ::temp0 label0 ;@line 11
            CALLMETHOD Is3DLoaded self ::temp0 ;@line 11
            ASSIGN ::temp0 ::temp0 ;@line 11
            label0:
            ASSIGN ::temp0 ::temp0 ;@line 11
            JUMPF ::temp0 label1 ;@line 11
            CAST ::temp1 self ;@line 11
            CALLSTATIC netImmerse HasNode ::temp0 ::temp1 "NPC" False ;@line 11
            ASSIGN ::temp0 ::temp0 ;@line 11
            label1:
            JUMPF ::temp0 label2 ;@line 11
            CAST ::temp1 self ;@line 12
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp2 ::temp1 "NPC" False ;@line 12
            ASSIGN current ::temp2 ;@line 12
            COMPAREEQ ::temp0 current expected ;@line 14
            JUMPF ::temp0 label3 ;@line 14
            CAST ::temp1 self ;@line 15
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp1 "NPC" baseline False ;@line 15
            CALLSTATIC debug Trace ::nonevar "VRM2Skyrim: seated height cleared" 0 ;@line 16
            JUMP label3 ;@line 16
            label3:
            JUMP label2 ;@line 16
            label2:
            ASSIGN applied False ;@line 19
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 85
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
            CAST ::temp0 self ;@line 25
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "IdleFurnitureStart" ;@line 25
            ASSIGN registered ::temp1 ;@line 25
            CAST ::temp0 self ;@line 26
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "IdleChairEnterStart" ;@line 26
            ASSIGN ::temp1 ::temp1 ;@line 26
            JUMPT ::temp1 label0 ;@line 26
            ASSIGN ::temp1 registered ;@line 26
            label0:
            ASSIGN registered ::temp1 ;@line 26
            CAST ::temp0 self ;@line 27
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "IdleLeftChairEnterStart" ;@line 27
            ASSIGN ::temp1 ::temp1 ;@line 27
            JUMPT ::temp1 label1 ;@line 27
            ASSIGN ::temp1 registered ;@line 27
            label1:
            ASSIGN registered ::temp1 ;@line 27
            CAST ::temp0 self ;@line 28
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "IdleRightChairEnterStart" ;@line 28
            ASSIGN ::temp1 ::temp1 ;@line 28
            JUMPT ::temp1 label2 ;@line 28
            ASSIGN ::temp1 registered ;@line 28
            label2:
            ASSIGN registered ::temp1 ;@line 28
            CAST ::temp0 self ;@line 29
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "SoundPlay.NPCHumanSitChairDown" ;@line 29
            ASSIGN ::temp1 ::temp1 ;@line 29
            JUMPT ::temp1 label3 ;@line 29
            ASSIGN ::temp1 registered ;@line 29
            label3:
            ASSIGN registered ::temp1 ;@line 29
            CAST ::temp0 self ;@line 30
            CALLMETHOD RegisterForAnimationEvent self ::temp1 ::temp0 "SoundPlay.NPCHumanSitChairDownLR" ;@line 30
            ASSIGN ::temp1 ::temp1 ;@line 30
            JUMPT ::temp1 label4 ;@line 30
            ASSIGN ::temp1 registered ;@line 30
            label4:
            ASSIGN registered ::temp1 ;@line 30
            NOT ::temp1 registered ;@line 31
            ASSIGN ::temp1 ::temp1 ;@line 31
            JUMPF ::temp1 label5 ;@line 31
            CALLMETHOD Is3DLoaded self ::temp1 ;@line 31
            ASSIGN ::temp1 ::temp1 ;@line 31
            label5:
            JUMPF ::temp1 label6 ;@line 31
            CALLSTATIC debug Trace ::nonevar "VRM2Skyrim: chair-entry events unavailable; OnSit fallback remains active" 0 ;@line 32
            JUMP label6 ;@line 32
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 93
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
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 72
            CALLMETHOD RegisterChairEvents self ::nonevar ;@line 73
            CALLMETHOD RefreshSeating self ::nonevar ;@line 74
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
            .local furniture objectReference
            .local ::temp2 objectReference
            .local ::temp3 form
            .local current Float
            .local ::temp4 Float
            .local ::nonevar None
            .local ::temp5 String
            .local ::temp6 String
          .endLocalTable
          .code
            CALLMETHOD Is3DLoaded self ::temp0 ;@line 37
            NOT ::temp0 ::temp0 ;@line 37
            JUMPF ::temp0 label0 ;@line 37
            RETURN None ;@line 38
            JUMP label0 ;@line 38
            label0:
            ASSIGN seated False ;@line 40
            CALLMETHOD GetSitState self ::temp1 ;@line 41
            ASSIGN sitState ::temp1 ;@line 41
            COMPAREEQ ::temp0 sitState 2 ;@line 42
            ASSIGN ::temp0 ::temp0 ;@line 42
            JUMPT ::temp0 label1 ;@line 42
            COMPAREEQ ::temp0 sitState 3 ;@line 42
            ASSIGN ::temp0 ::temp0 ;@line 42
            label1:
            ASSIGN ::temp0 ::temp0 ;@line 42
            JUMPF ::temp0 label2 ;@line 42
            CALLMETHOD GetSleepState self ::temp1 ;@line 42
            COMPAREEQ ::temp0 ::temp1 0 ;@line 42
            ASSIGN ::temp0 ::temp0 ;@line 42
            label2:
            ASSIGN ::temp0 ::temp0 ;@line 42
            JUMPF ::temp0 label3 ;@line 42
            CALLMETHOD IsOnMount self ::temp0 ;@line 42
            NOT ::temp0 ::temp0 ;@line 42
            ASSIGN ::temp0 ::temp0 ;@line 42
            label3:
            JUMPF ::temp0 label4 ;@line 42
            CALLMETHOD GetFurnitureReference self ::temp2 ;@line 43
            ASSIGN furniture ::temp2 ;@line 43
            CAST ::temp0 furniture ;@line 44
            ASSIGN ::temp0 ::temp0 ;@line 44
            JUMPF ::temp0 label5 ;@line 44
            CALLMETHOD GetBaseObject furniture ::temp3 ;@line 44
            CALLMETHOD HasForm ::Seats_var ::temp0 ::temp3 ;@line 44
            ASSIGN ::temp0 ::temp0 ;@line 44
            label5:
            JUMPF ::temp0 label6 ;@line 44
            ASSIGN seated True ;@line 45
            JUMP label6 ;@line 45
            label6:
            JUMP label4 ;@line 45
            label4:
            CAST ::temp2 self ;@line 48
            CALLSTATIC netImmerse HasNode ::temp0 ::temp2 "NPC" False ;@line 48
            JUMPF ::temp0 label7 ;@line 48
            ASSIGN ::temp0 seated ;@line 49
            JUMPF ::temp0 label8 ;@line 49
            COMPAREEQ ::temp0 ::Offset_var 0.000000 ;@line 49
            NOT ::temp0 ::temp0 ;@line 49
            ASSIGN ::temp0 ::temp0 ;@line 49
            label8:
            JUMPF ::temp0 label9 ;@line 49
            CAST ::temp2 self ;@line 50
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp4 ::temp2 "NPC" False ;@line 50
            ASSIGN current ::temp4 ;@line 50
            NOT ::temp0 applied ;@line 51
            JUMPF ::temp0 label10 ;@line 51
            ASSIGN baseline current ;@line 52
            FADD ::temp4 baseline ::Offset_var ;@line 53
            ASSIGN expected ::temp4 ;@line 53
            CAST ::temp2 self ;@line 54
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp2 "NPC" expected False ;@line 54
            ASSIGN applied True ;@line 55
            CAST ::temp5 ::Offset_var ;@line 56
            STRCAT ::temp5 "VRM2Skyrim: chair height=" ::temp5 ;@line 56
            STRCAT ::temp5 ::temp5 "; sitState=" ;@line 56
            CAST ::temp6 sitState ;@line 56
            STRCAT ::temp6 ::temp5 ::temp6 ;@line 56
            CALLSTATIC debug Trace ::nonevar ::temp6 0 ;@line 56
            JUMP label11 ;@line 56
            label10:
            COMPAREEQ ::temp0 current baseline ;@line 57
            JUMPF ::temp0 label11 ;@line 57
            CAST ::temp2 self ;@line 59
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp2 "NPC" expected False ;@line 59
            JUMP label11 ;@line 59
            label11:
            JUMP label12 ;@line 59
            label9:
            CALLMETHOD ClearCorrection self ::nonevar ;@line 62
            label12:
            JUMP label7 ;@line 62
            label7:
            COMPAREEQ ::temp0 sitState 2 ;@line 66
            ASSIGN ::temp0 ::temp0 ;@line 66
            JUMPT ::temp0 label13 ;@line 66
            COMPAREEQ ::temp0 sitState 3 ;@line 66
            ASSIGN ::temp0 ::temp0 ;@line 66
            label13:
            ASSIGN ::temp0 ::temp0 ;@line 66
            JUMPT ::temp0 label14 ;@line 66
            COMPAREEQ ::temp0 sitState 4 ;@line 66
            ASSIGN ::temp0 ::temp0 ;@line 66
            label14:
            JUMPF ::temp0 label15 ;@line 66
            CALLMETHOD RegisterForSingleUpdate self ::nonevar 0.500000 ;@line 67
            JUMP label15 ;@line 67
            label15:
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
            CALLMETHOD ClearCorrection self ::nonevar ;@line 78
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 79
            CALLMETHOD RegisterChairEvents self ::nonevar ;@line 80
            CALLMETHOD RefreshSeating self ::nonevar ;@line 81
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
          .endLocalTable
          .code
            CAST ::temp0 self ;@line 97
            COMPAREEQ ::temp1 akSource ::temp0 ;@line 97
            JUMPF ::temp1 label0 ;@line 97
            COMPAREEQ ::temp1 asEventName "IdleFurnitureStart" ;@line 98
            ASSIGN ::temp1 ::temp1 ;@line 98
            JUMPT ::temp1 label1 ;@line 98
            COMPAREEQ ::temp1 asEventName "IdleChairEnterStart" ;@line 98
            ASSIGN ::temp1 ::temp1 ;@line 98
            label1:
            ASSIGN ::temp1 ::temp1 ;@line 98
            JUMPT ::temp1 label2 ;@line 98
            COMPAREEQ ::temp1 asEventName "IdleLeftChairEnterStart" ;@line 98
            ASSIGN ::temp1 ::temp1 ;@line 98
            label2:
            ASSIGN ::temp1 ::temp1 ;@line 98
            JUMPT ::temp1 label3 ;@line 98
            COMPAREEQ ::temp1 asEventName "IdleRightChairEnterStart" ;@line 98
            ASSIGN ::temp1 ::temp1 ;@line 98
            label3:
            ASSIGN ::temp1 ::temp1 ;@line 98
            JUMPT ::temp1 label4 ;@line 98
            COMPAREEQ ::temp1 asEventName "SoundPlay.NPCHumanSitChairDown" ;@line 98
            ASSIGN ::temp1 ::temp1 ;@line 98
            label4:
            ASSIGN ::temp1 ::temp1 ;@line 98
            JUMPT ::temp1 label5 ;@line 98
            COMPAREEQ ::temp1 asEventName "SoundPlay.NPCHumanSitChairDownLR" ;@line 98
            ASSIGN ::temp1 ::temp1 ;@line 98
            label5:
            JUMPF ::temp1 label6 ;@line 98
            CALLMETHOD GetSitState self ::temp2 ;@line 101
            COMPAREEQ ::temp1 ::temp2 0 ;@line 101
            JUMPF ::temp1 label7 ;@line 101
            CALLMETHOD RegisterForSingleUpdate self ::nonevar 0.100000 ;@line 102
            JUMP label8 ;@line 102
            label7:
            CALLMETHOD RefreshSeating self ::nonevar ;@line 104
            label8:
            JUMP label6 ;@line 104
            label6:
            JUMP label0 ;@line 104
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
            CALLMETHOD UnregisterForUpdate self ::nonevar ;@line 123
            CALLMETHOD ClearCorrection self ::nonevar ;@line 124
          .endCode
        .endFunction
      .endState
    .endStateTable
  .endObject
.endObjectTable
