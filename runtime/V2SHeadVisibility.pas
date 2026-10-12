.info
.source "V2SHeadVisibility.psc"
  .modifyTime 0
  .compileTime 1791807550
.user "VRM2Skyrim"
.computer "VRM2Skyrim"
.endInfo
.userFlagsRef
.endUserFlagsRef
.objectTable
  .object V2SHeadVisibility Actor
    .userFlags 0
    .docString ""
    .autoState
    .structTable
    .endStructTable
    .variableTable
      .variable ::FullSkin_var armor
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::FaceHiddenSkin_var armor
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::HairHiddenSkin_var armor
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::BothHiddenSkin_var armor
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::FaceHidingEquipment_var formList
        .userFlags 0
        .initialValue None
      .endVariable
      .variable ::HairHidingEquipment_var formList
        .userFlags 0
        .initialValue None
      .endVariable
    .endVariableTable
    .guardTable
    .endGuardTable
    .propertyTable
      .property FullSkin armor auto
        .userFlags 0
        .docString ""
        .autoVar ::FullSkin_var
      .endProperty
      .property FaceHiddenSkin armor auto
        .userFlags 0
        .docString ""
        .autoVar ::FaceHiddenSkin_var
      .endProperty
      .property HairHiddenSkin armor auto
        .userFlags 0
        .docString ""
        .autoVar ::HairHiddenSkin_var
      .endProperty
      .property BothHiddenSkin armor auto
        .userFlags 0
        .docString ""
        .autoVar ::BothHiddenSkin_var
      .endProperty
      .property FaceHidingEquipment formList auto
        .userFlags 0
        .docString ""
        .autoVar ::FaceHidingEquipment_var
      .endProperty
      .property HairHidingEquipment formList auto
        .userFlags 0
        .docString ""
        .autoVar ::HairHidingEquipment_var
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
        .function AnyEquipped
          .userFlags 0
          .docString ""
          .return Bool
          .paramTable
            .param items formList
          .endParamTable
          .localTable
            .local i Int
            .local mask Int
            .local ::temp0 Bool
            .local worn form
            .local ::temp1 form
            .local ::temp2 Int
          .endLocalTable
          .code
            ASSIGN i 0 ;@line 11
            ASSIGN mask 1 ;@line 12
            label3:
            COMPARELT ::temp0 i 32 ;@line 14
            JUMPF ::temp0 label0 ;@line 14
            CALLMETHOD GetWornForm self ::temp1 mask ;@line 15
            ASSIGN worn ::temp1 ;@line 15
            CAST ::temp0 worn ;@line 16
            ASSIGN ::temp0 ::temp0 ;@line 16
            JUMPF ::temp0 label1 ;@line 16
            CALLMETHOD HasForm items ::temp0 worn ;@line 16
            ASSIGN ::temp0 ::temp0 ;@line 16
            label1:
            JUMPF ::temp0 label2 ;@line 16
            RETURN True ;@line 17
            JUMP label2 ;@line 17
            label2:
            IADD ::temp2 i 1 ;@line 19
            ASSIGN i ::temp2 ;@line 19
            IMULTIPLY ::temp2 mask 2 ;@line 20
            ASSIGN mask ::temp2 ;@line 20
            JUMP label3 ;@line 20
            label0:
            RETURN False ;@line 22
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
            CAST ::temp0 self ;@line 63
            COMPAREEQ ::temp1 akActor ::temp0 ;@line 63
            JUMPF ::temp1 label0 ;@line 63
            CALLMETHOD RefreshVisibility self ::nonevar ;@line 64
            JUMP label0 ;@line 64
            label0:
          .endCode
        .endFunction
        .function OnObjectUnequipped
          .userFlags 0
          .docString ""
          .return None
          .paramTable
            .param akBaseObject form
            .param akReference objectReference
          .endParamTable
          .localTable
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD RefreshVisibility self ::nonevar ;@line 59
          .endCode
        .endFunction
        .function RefreshVisibility
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local face Bool
            .local ::temp0 Bool
            .local hair Bool
            .local desired armor
            .local base actorBase
            .local ::temp1 actorBase
            .local ::temp2 armor
            .local ::nonevar None
            .local ::temp3 String
          .endLocalTable
          .code
            CALLMETHOD AnyEquipped self ::temp0 ::FaceHidingEquipment_var ;@line 26
            ASSIGN face ::temp0 ;@line 26
            CALLMETHOD AnyEquipped self ::temp0 ::HairHidingEquipment_var ;@line 27
            ASSIGN hair ::temp0 ;@line 27
            ASSIGN desired ::FullSkin_var ;@line 28
            ASSIGN ::temp0 face ;@line 29
            JUMPF ::temp0 label0 ;@line 29
            ASSIGN ::temp0 hair ;@line 29
            label0:
            JUMPF ::temp0 label1 ;@line 29
            ASSIGN desired ::BothHiddenSkin_var ;@line 30
            JUMP label2 ;@line 30
            label1:
            JUMPF face label3 ;@line 30
            ASSIGN desired ::FaceHiddenSkin_var ;@line 32
            JUMP label2 ;@line 32
            label3:
            JUMPF hair label2 ;@line 32
            ASSIGN desired ::HairHiddenSkin_var ;@line 34
            JUMP label2 ;@line 34
            label2:
            CALLMETHOD GetActorBase self ::temp1 ;@line 36
            ASSIGN base ::temp1 ;@line 36
            CAST ::temp0 base ;@line 37
            ASSIGN ::temp0 ::temp0 ;@line 37
            JUMPF ::temp0 label4 ;@line 37
            CALLMETHOD GetSkin base ::temp2 ;@line 37
            COMPAREEQ ::temp0 ::temp2 desired ;@line 37
            NOT ::temp0 ::temp0 ;@line 37
            ASSIGN ::temp0 ::temp0 ;@line 37
            label4:
            JUMPF ::temp0 label5 ;@line 37
            CALLMETHOD SetSkin base ::nonevar desired ;@line 38
            CALLMETHOD QueueNiNodeUpdate self ::nonevar ;@line 39
            CAST ::temp3 desired ;@line 40
            STRCAT ::temp3 "VRM2Skyrim: head visibility skin=" ::temp3 ;@line 40
            CALLSTATIC debug Trace ::nonevar ::temp3 0 ;@line 40
            JUMP label5 ;@line 40
            label5:
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
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 45
            CALLMETHOD RefreshVisibility self ::nonevar ;@line 46
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
            CALLMETHOD RegisterForNiNodeUpdate self ::nonevar ;@line 50
            CALLMETHOD RefreshVisibility self ::nonevar ;@line 51
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
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD RefreshVisibility self ::nonevar ;@line 55
          .endCode
        .endFunction
      .endState
    .endStateTable
  .endObject
.endObjectTable
