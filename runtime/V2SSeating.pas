.info
  .source "C:\\Users\\shuhe\\workspace\\games\\vrm-skyrim-converter\\runtime\\V2SSeating.psc"
  .modifyTime 0
  .compileTime 1791997890
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 73
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
            .local ::temp2 Float
            .local ::nonevar None
          .endLocalTable
          .code
            CAST ::temp0 self ;@line 81
            COMPAREEQ ::temp1 akActor ::temp0 ;@line 81
            JUMPF ::temp1 label0 ;@line 81
            ASSIGN ::temp1 applied ;@line 82
            JUMPF ::temp1 label1 ;@line 82
            CALLMETHOD Is3DLoaded self ::temp1 ;@line 82
            ASSIGN ::temp1 ::temp1 ;@line 82
            label1:
            ASSIGN ::temp1 ::temp1 ;@line 82
            JUMPF ::temp1 label2 ;@line 82
            CAST ::temp0 self ;@line 82
            CALLSTATIC netImmerse HasNode ::temp1 ::temp0 "NPC" False ;@line 82
            ASSIGN ::temp1 ::temp1 ;@line 82
            label2:
            JUMPF ::temp1 label3 ;@line 82
            CAST ::temp0 self ;@line 83
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp2 ::temp0 "NPC" False ;@line 83
            COMPAREEQ ::temp1 ::temp2 expected ;@line 83
            NOT ::temp1 ::temp1 ;@line 83
            JUMPF ::temp1 label4 ;@line 83
            ASSIGN applied False ;@line 84
            JUMP label4 ;@line 84
            label4:
            JUMP label3 ;@line 84
            label3:
            CALLMETHOD RefreshSeating self ::nonevar ;@line 87
            JUMP label0 ;@line 87
            label0:
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 69
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 77
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
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 58
            CALLMETHOD RefreshSeating self ::nonevar ;@line 59
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
          .endLocalTable
          .code
            CALLMETHOD Is3DLoaded self ::temp0 ;@line 23
            NOT ::temp0 ::temp0 ;@line 23
            JUMPF ::temp0 label0 ;@line 23
            RETURN None ;@line 24
            JUMP label0 ;@line 24
            label0:
            ASSIGN seated False ;@line 26
            CALLMETHOD GetSitState self ::temp1 ;@line 27
            ASSIGN sitState ::temp1 ;@line 27
            COMPAREEQ ::temp0 sitState 3 ;@line 28
            ASSIGN ::temp0 ::temp0 ;@line 28
            JUMPF ::temp0 label1 ;@line 28
            CALLMETHOD GetSleepState self ::temp1 ;@line 28
            COMPAREEQ ::temp0 ::temp1 0 ;@line 28
            ASSIGN ::temp0 ::temp0 ;@line 28
            label1:
            ASSIGN ::temp0 ::temp0 ;@line 28
            JUMPF ::temp0 label2 ;@line 28
            CALLMETHOD IsOnMount self ::temp0 ;@line 28
            NOT ::temp0 ::temp0 ;@line 28
            ASSIGN ::temp0 ::temp0 ;@line 28
            label2:
            JUMPF ::temp0 label3 ;@line 28
            CALLMETHOD GetFurnitureReference self ::temp2 ;@line 29
            ASSIGN furniture ::temp2 ;@line 29
            CAST ::temp0 furniture ;@line 30
            ASSIGN ::temp0 ::temp0 ;@line 30
            JUMPF ::temp0 label4 ;@line 30
            CALLMETHOD GetBaseObject furniture ::temp3 ;@line 30
            CALLMETHOD HasForm ::Seats_var ::temp0 ::temp3 ;@line 30
            ASSIGN ::temp0 ::temp0 ;@line 30
            label4:
            JUMPF ::temp0 label5 ;@line 30
            ASSIGN seated True ;@line 31
            JUMP label5 ;@line 31
            label5:
            JUMP label3 ;@line 31
            label3:
            CAST ::temp2 self ;@line 34
            CALLSTATIC netImmerse HasNode ::temp0 ::temp2 "NPC" False ;@line 34
            JUMPF ::temp0 label6 ;@line 34
            ASSIGN ::temp0 seated ;@line 35
            JUMPF ::temp0 label7 ;@line 35
            COMPAREEQ ::temp0 ::Offset_var 0.000000 ;@line 35
            NOT ::temp0 ::temp0 ;@line 35
            ASSIGN ::temp0 ::temp0 ;@line 35
            label7:
            JUMPF ::temp0 label8 ;@line 35
            CAST ::temp2 self ;@line 36
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp4 ::temp2 "NPC" False ;@line 36
            ASSIGN current ::temp4 ;@line 36
            NOT ::temp0 applied ;@line 37
            JUMPF ::temp0 label9 ;@line 37
            ASSIGN baseline current ;@line 38
            FADD ::temp4 baseline ::Offset_var ;@line 39
            ASSIGN expected ::temp4 ;@line 39
            CAST ::temp2 self ;@line 40
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp2 "NPC" expected False ;@line 40
            ASSIGN applied True ;@line 41
            CAST ::temp5 ::Offset_var ;@line 42
            STRCAT ::temp5 "VRM2Skyrim: seated height=" ::temp5 ;@line 42
            CALLSTATIC debug Trace ::nonevar ::temp5 0 ;@line 42
            JUMP label10 ;@line 42
            label9:
            COMPAREEQ ::temp0 current baseline ;@line 43
            JUMPF ::temp0 label10 ;@line 43
            CAST ::temp2 self ;@line 45
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp2 "NPC" expected False ;@line 45
            JUMP label10 ;@line 45
            label10:
            JUMP label11 ;@line 45
            label8:
            CALLMETHOD ClearCorrection self ::nonevar ;@line 48
            label11:
            JUMP label6 ;@line 48
            label6:
            COMPAREEQ ::temp0 sitState 2 ;@line 52
            ASSIGN ::temp0 ::temp0 ;@line 52
            JUMPT ::temp0 label12 ;@line 52
            COMPAREEQ ::temp0 sitState 3 ;@line 52
            ASSIGN ::temp0 ::temp0 ;@line 52
            label12:
            ASSIGN ::temp0 ::temp0 ;@line 52
            JUMPT ::temp0 label13 ;@line 52
            COMPAREEQ ::temp0 sitState 4 ;@line 52
            ASSIGN ::temp0 ::temp0 ;@line 52
            label13:
            JUMPF ::temp0 label14 ;@line 52
            CALLMETHOD RegisterForSingleUpdate self ::nonevar 0.500000 ;@line 53
            JUMP label14 ;@line 53
            label14:
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
            CALLMETHOD ClearCorrection self ::nonevar ;@line 63
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 64
            CALLMETHOD RefreshSeating self ::nonevar ;@line 65
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
            CALLMETHOD UnregisterForUpdate self ::nonevar ;@line 92
            CALLMETHOD ClearCorrection self ::nonevar ;@line 93
          .endCode
        .endFunction
      .endState
    .endStateTable
  .endObject
.endObjectTable
