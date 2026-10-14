.info
  .source "C:\\Users\\shuhe\\workspace\\games\\vrm-skyrim-converter\\runtime\\V2SSeating.psc"
  .modifyTime 0
  .compileTime 1791995722
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 50
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
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 32
            CALLMETHOD RefreshSeating self ::nonevar ;@line 33
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
            .local desired Float
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
            CALLMETHOD Is3DLoaded self ::temp0 ;@line 7
            NOT ::temp0 ::temp0 ;@line 7
            JUMPF ::temp0 label0 ;@line 7
            RETURN None ;@line 8
            JUMP label0 ;@line 8
            label0:
            ASSIGN desired 0.000000 ;@line 10
            CALLMETHOD GetSitState self ::temp1 ;@line 11
            ASSIGN sitState ::temp1 ;@line 11
            COMPAREEQ ::temp0 sitState 3 ;@line 12
            ASSIGN ::temp0 ::temp0 ;@line 12
            JUMPF ::temp0 label1 ;@line 12
            CALLMETHOD GetSleepState self ::temp1 ;@line 12
            COMPAREEQ ::temp0 ::temp1 0 ;@line 12
            ASSIGN ::temp0 ::temp0 ;@line 12
            label1:
            ASSIGN ::temp0 ::temp0 ;@line 12
            JUMPF ::temp0 label2 ;@line 12
            CALLMETHOD IsOnMount self ::temp0 ;@line 12
            NOT ::temp0 ::temp0 ;@line 12
            ASSIGN ::temp0 ::temp0 ;@line 12
            label2:
            JUMPF ::temp0 label3 ;@line 12
            CALLMETHOD GetFurnitureReference self ::temp2 ;@line 13
            ASSIGN furniture ::temp2 ;@line 13
            CAST ::temp0 furniture ;@line 14
            ASSIGN ::temp0 ::temp0 ;@line 14
            JUMPF ::temp0 label4 ;@line 14
            CALLMETHOD GetBaseObject furniture ::temp3 ;@line 14
            CALLMETHOD HasForm ::Seats_var ::temp0 ::temp3 ;@line 14
            ASSIGN ::temp0 ::temp0 ;@line 14
            label4:
            JUMPF ::temp0 label5 ;@line 14
            ASSIGN desired ::Offset_var ;@line 15
            JUMP label5 ;@line 15
            label5:
            JUMP label3 ;@line 15
            label3:
            CAST ::temp2 self ;@line 18
            CALLSTATIC netImmerse HasNode ::temp0 ::temp2 "VRM2SkyrimSeating" False ;@line 18
            JUMPF ::temp0 label6 ;@line 18
            CAST ::temp2 self ;@line 19
            CALLSTATIC netImmerse GetNodeLocalPositionZ ::temp4 ::temp2 "VRM2SkyrimSeating" False ;@line 19
            ASSIGN current ::temp4 ;@line 19
            COMPAREEQ ::temp0 current desired ;@line 20
            NOT ::temp0 ::temp0 ;@line 20
            JUMPF ::temp0 label7 ;@line 20
            CAST ::temp2 self ;@line 21
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp2 "VRM2SkyrimSeating" desired False ;@line 21
            CAST ::temp5 desired ;@line 22
            STRCAT ::temp5 "VRM2Skyrim: seated height=" ::temp5 ;@line 22
            CALLSTATIC debug Trace ::nonevar ::temp5 0 ;@line 22
            JUMP label7 ;@line 22
            label7:
            JUMP label6 ;@line 22
            label6:
            COMPAREEQ ::temp0 sitState 2 ;@line 26
            ASSIGN ::temp0 ::temp0 ;@line 26
            JUMPT ::temp0 label8 ;@line 26
            COMPAREEQ ::temp0 sitState 3 ;@line 26
            ASSIGN ::temp0 ::temp0 ;@line 26
            label8:
            ASSIGN ::temp0 ::temp0 ;@line 26
            JUMPT ::temp0 label9 ;@line 26
            COMPAREEQ ::temp0 sitState 4 ;@line 26
            ASSIGN ::temp0 ::temp0 ;@line 26
            label9:
            JUMPF ::temp0 label10 ;@line 26
            CALLMETHOD RegisterForSingleUpdate self ::nonevar 0.500000 ;@line 27
            JUMP label10 ;@line 27
            label10:
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
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 37
            CALLMETHOD RefreshSeating self ::nonevar ;@line 38
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
          .endLocalTable
          .code
            CAST ::temp0 self ;@line 54
            COMPAREEQ ::temp1 akActor ::temp0 ;@line 54
            JUMPF ::temp1 label0 ;@line 54
            CALLMETHOD RefreshSeating self ::nonevar ;@line 55
            JUMP label0 ;@line 55
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 46
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
            CALLMETHOD RefreshSeating self ::nonevar ;@line 42
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
            .local ::temp0 Bool
            .local ::temp1 objectReference
          .endLocalTable
          .code
            CALLMETHOD UnregisterForUpdate self ::nonevar ;@line 60
            CALLMETHOD Is3DLoaded self ::temp0 ;@line 61
            ASSIGN ::temp0 ::temp0 ;@line 61
            JUMPF ::temp0 label0 ;@line 61
            CAST ::temp1 self ;@line 61
            CALLSTATIC netImmerse HasNode ::temp0 ::temp1 "VRM2SkyrimSeating" False ;@line 61
            ASSIGN ::temp0 ::temp0 ;@line 61
            label0:
            JUMPF ::temp0 label1 ;@line 61
            CAST ::temp1 self ;@line 62
            CALLSTATIC netImmerse SetNodeLocalPositionZ ::nonevar ::temp1 "VRM2SkyrimSeating" 0.000000 False ;@line 62
            JUMP label1 ;@line 62
            label1:
          .endCode
        .endFunction
      .endState
    .endStateTable
  .endObject
.endObjectTable
