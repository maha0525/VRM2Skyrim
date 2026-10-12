.info
  .source "C:\\Users\\shuhe\\workspace\\games\\vrm-skyrim-converter\\runtime\\V2SInitialWardrobe.psc"
  .modifyTime 0
  .compileTime 1791829386
  .user "shuhe"
  .computer "SAIV-EARTH"
.endInfo
.userFlagsRef
.endUserFlagsRef
.objectTable
  .object V2SInitialWardrobe Actor
    .userFlags 0
    .docString ""
    .autoState
    .structTable
    .endStructTable
    .variableTable
      .variable initialized Bool
        .userFlags 0
        .initialValue False
      .endVariable
      .variable ::InitialItems_var formList
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::BodyClothes_var formList
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::HandsClothes_var formList
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::FeetClothes_var formList
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::BodyEquipment_var formList
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::HandsEquipment_var formList
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::FeetEquipment_var formList
        .userFlags 0
        .initialValue None
      .endVariable
    .endVariableTable
    .guardTable
    .endGuardTable
    .propertyTable
      .property InitialItems formList auto
        .userFlags 0
        .docString ""
        .autoVar ::InitialItems_var
      .endProperty
      .property BodyClothes formList auto
        .userFlags 0
        .docString ""
        .autoVar ::BodyClothes_var
      .endProperty
      .property HandsClothes formList auto
        .userFlags 0
        .docString ""
        .autoVar ::HandsClothes_var
      .endProperty
      .property FeetClothes formList auto
        .userFlags 0
        .docString ""
        .autoVar ::FeetClothes_var
      .endProperty
      .property BodyEquipment formList auto
        .userFlags 0
        .docString ""
        .autoVar ::BodyEquipment_var
      .endProperty
      .property HandsEquipment formList auto
        .userFlags 0
        .docString ""
        .autoVar ::HandsEquipment_var
      .endProperty
      .property FeetEquipment formList auto
        .userFlags 0
        .docString ""
        .autoVar ::FeetEquipment_var
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
        .function UnequipConflicts
          .userFlags 0
          .docString ""
          .return None
          .paramTable
            .param items formList
          .endParamTable
          .localTable
          .endLocalTable
          .code
          .endCode
        .endFunction
        .function OnInit
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local ::temp0 Bool
            .local ::nonevar None
            .local i Int
            .local ::temp1 Int
            .local item form
            .local ::temp2 form
          .endLocalTable
          .code
            JUMPF initialized label0 ;@line 15
            RETURN None ;@line 16
            JUMP label0 ;@line 16
            label0:
            ASSIGN initialized True ;@line 18
            CALLMETHOD IsPlayerTeammate self ::temp0 ;@line 19
            JUMPF ::temp0 label1 ;@line 19
            CALLSTATIC debug Trace ::nonevar "VRM2Skyrim: initial equip skipped for existing teammate; native slots own equipment" 0 ;@line 20
            RETURN None ;@line 21
            JUMP label1 ;@line 21
            label1:
            ASSIGN i 0 ;@line 23
            label5:
            CALLMETHOD GetSize ::InitialItems_var ::temp1 ;@line 24
            COMPARELT ::temp0 i ::temp1 ;@line 24
            JUMPF ::temp0 label2 ;@line 24
            CALLMETHOD GetAt ::InitialItems_var ::temp2 i ;@line 25
            ASSIGN item ::temp2 ;@line 25
            CAST ::temp0 item ;@line 26
            ASSIGN ::temp0 ::temp0 ;@line 26
            JUMPF ::temp0 label3 ;@line 26
            CALLMETHOD GetItemCount self ::temp1 item ;@line 26
            COMPAREGT ::temp0 ::temp1 0 ;@line 26
            ASSIGN ::temp0 ::temp0 ;@line 26
            label3:
            JUMPF ::temp0 label4 ;@line 26
            CALLMETHOD EquipItem self ::nonevar item False True ;@line 27
            JUMP label4 ;@line 27
            label4:
            IADD ::temp1 i 1 ;@line 29
            ASSIGN i ::temp1 ;@line 29
            JUMP label5 ;@line 29
            label2:
            CALLSTATIC debug Trace ::nonevar "VRM2Skyrim: initial clothes equipped once; replacement uses native slots" 0 ;@line 31
          .endCode
        .endFunction
        .function ResolveCurrentEquipment
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
          .endLocalTable
          .code
          .endCode
        .endFunction
        .function AnyEquipped
          .userFlags 0
          .docString ""
          .return Bool
          .paramTable
            .param items formList
            .param slotMask Int
          .endParamTable
          .localTable
          .endLocalTable
          .code
            RETURN False ;@line 36
          .endCode
        .endFunction
        .function OnLoad
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
          .endLocalTable
          .code
          .endCode
        .endFunction
        .function OnObjectEquipped
          .userFlags 0
          .docString ""
          .return None
          .paramTable
            .param akBaseObject form
            .param akReference objectReference
          .endParamTable
          .localTable
          .endLocalTable
          .code
          .endCode
        .endFunction
      .endState
    .endStateTable
  .endObject
.endObjectTable
