.info
  .source "V2SInitialWardrobe.psc"
  .modifyTime 0
  .compileTime 1791776866
  .user "VRM2Skyrim"
  .computer "VRM2Skyrim"
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
            .local i Int
            .local ::temp0 Int
            .local ::temp1 Bool
            .local item form
            .local ::temp2 form
            .local ::nonevar None
            .local ::temp3 String
          .endLocalTable
          .code
            ASSIGN i 0 ;@line 64
            label3:
            CALLMETHOD GetSize items ::temp0 ;@line 65
            COMPARELT ::temp1 i ::temp0 ;@line 65
            JUMPF ::temp1 label0 ;@line 65
            CALLMETHOD GetAt items ::temp2 i ;@line 66
            ASSIGN item ::temp2 ;@line 66
            CAST ::temp1 item ;@line 67
            ASSIGN ::temp1 ::temp1 ;@line 67
            JUMPF ::temp1 label1 ;@line 67
            CALLMETHOD IsEquipped self ::temp1 item ;@line 67
            ASSIGN ::temp1 ::temp1 ;@line 67
            label1:
            JUMPF ::temp1 label2 ;@line 67
            CALLMETHOD UnequipItem self ::nonevar item False True ;@line 68
            CAST ::temp3 item ;@line 69
            STRCAT ::temp3 "VRM2Skyrim: unequipped conflicting garment/equipment " ::temp3 ;@line 69
            CALLSTATIC debug Trace ::nonevar ::temp3 0 ;@line 69
            JUMP label2 ;@line 69
            label2:
            IADD ::temp0 i 1 ;@line 71
            ASSIGN i ::temp0 ;@line 71
            JUMP label3 ;@line 71
            label0:
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
            JUMPF initialized label0 ;@line 14
            RETURN None ;@line 15
            JUMP label0 ;@line 15
            label0:
            ASSIGN initialized True ;@line 17
            CALLMETHOD IsPlayerTeammate self ::temp0 ;@line 19
            JUMPF ::temp0 label1 ;@line 19
            CALLMETHOD ResolveCurrentEquipment self ::nonevar ;@line 20
            CALLSTATIC debug Trace ::nonevar "VRM2Skyrim: initial wardrobe skipped for existing teammate" 0 ;@line 21
            RETURN None ;@line 22
            JUMP label1 ;@line 22
            label1:
            ASSIGN i 0 ;@line 24
            label5:
            CALLMETHOD GetSize ::InitialItems_var ::temp1 ;@line 25
            COMPARELT ::temp0 i ::temp1 ;@line 25
            JUMPF ::temp0 label2 ;@line 25
            CALLMETHOD GetAt ::InitialItems_var ::temp2 i ;@line 26
            ASSIGN item ::temp2 ;@line 26
            CAST ::temp0 item ;@line 27
            ASSIGN ::temp0 ::temp0 ;@line 27
            JUMPF ::temp0 label3 ;@line 27
            CALLMETHOD GetItemCount self ::temp1 item ;@line 27
            COMPAREGT ::temp0 ::temp1 0 ;@line 27
            ASSIGN ::temp0 ::temp0 ;@line 27
            label3:
            JUMPF ::temp0 label4 ;@line 27
            CALLMETHOD EquipItem self ::nonevar item False True ;@line 28
            JUMP label4 ;@line 28
            label4:
            IADD ::temp1 i 1 ;@line 30
            ASSIGN i ::temp1 ;@line 30
            JUMP label5 ;@line 30
            label2:
            CALLSTATIC debug Trace ::nonevar "VRM2Skyrim: initial wardrobe equipped once" 0 ;@line 32
          .endCode
        .endFunction
        .function ResolveCurrentEquipment
          .userFlags 0
          .docString ""
          .return None
          .paramTable
          .endParamTable
          .localTable
            .local ::temp0 Bool
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD AnyEquipped self ::temp0 ::BodyEquipment_var ;@line 47
            JUMPF ::temp0 label0 ;@line 47
            CALLMETHOD UnequipConflicts self ::nonevar ::BodyClothes_var ;@line 48
            JUMP label0 ;@line 48
            label0:
            CALLMETHOD AnyEquipped self ::temp0 ::HandsEquipment_var ;@line 50
            JUMPF ::temp0 label1 ;@line 50
            CALLMETHOD UnequipConflicts self ::nonevar ::HandsClothes_var ;@line 51
            JUMP label1 ;@line 51
            label1:
            CALLMETHOD AnyEquipped self ::temp0 ::FeetEquipment_var ;@line 53
            JUMPF ::temp0 label2 ;@line 53
            CALLMETHOD UnequipConflicts self ::nonevar ::FeetClothes_var ;@line 54
            JUMP label2 ;@line 54
            label2:
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
            .local ::temp0 Int
            .local ::temp1 Bool
            .local ::temp2 form
          .endLocalTable
          .code
            ASSIGN i 0 ;@line 36
            label2:
            CALLMETHOD GetSize items ::temp0 ;@line 37
            COMPARELT ::temp1 i ::temp0 ;@line 37
            JUMPF ::temp1 label0 ;@line 37
            CALLMETHOD GetAt items ::temp2 i ;@line 38
            CALLMETHOD IsEquipped self ::temp1 ::temp2 ;@line 38
            JUMPF ::temp1 label1 ;@line 38
            RETURN True ;@line 39
            JUMP label1 ;@line 39
            label1:
            IADD ::temp0 i 1 ;@line 41
            ASSIGN i ::temp0 ;@line 41
            JUMP label2 ;@line 41
            label0:
            RETURN False ;@line 43
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
            CALLMETHOD ResolveCurrentEquipment self ::nonevar ;@line 60
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
            .local ::temp0 Bool
            .local ::nonevar None
          .endLocalTable
          .code
            CALLMETHOD IsEquipped self ::temp0 akBaseObject ;@line 77
            NOT ::temp0 ::temp0 ;@line 77
            JUMPF ::temp0 label0 ;@line 77
            RETURN None ;@line 78
            JUMP label0 ;@line 78
            label0:
            CALLMETHOD HasForm ::BodyEquipment_var ::temp0 akBaseObject ;@line 80
            JUMPF ::temp0 label1 ;@line 80
            CALLMETHOD UnequipConflicts self ::nonevar ::BodyClothes_var ;@line 81
            JUMP label2 ;@line 81
            label1:
            CALLMETHOD HasForm ::HandsEquipment_var ::temp0 akBaseObject ;@line 82
            JUMPF ::temp0 label3 ;@line 82
            CALLMETHOD UnequipConflicts self ::nonevar ::HandsClothes_var ;@line 83
            JUMP label2 ;@line 83
            label3:
            CALLMETHOD HasForm ::FeetEquipment_var ::temp0 akBaseObject ;@line 84
            JUMPF ::temp0 label4 ;@line 84
            CALLMETHOD UnequipConflicts self ::nonevar ::FeetClothes_var ;@line 85
            JUMP label2 ;@line 85
            label4:
            CALLMETHOD HasForm ::BodyClothes_var ::temp0 akBaseObject ;@line 86
            JUMPF ::temp0 label5 ;@line 86
            CALLMETHOD AnyEquipped self ::temp0 ::BodyEquipment_var ;@line 87
            JUMPF ::temp0 label6 ;@line 87
            CALLMETHOD UnequipConflicts self ::nonevar ::BodyClothes_var ;@line 88
            JUMP label6 ;@line 88
            label6:
            JUMP label2 ;@line 88
            label5:
            CALLMETHOD HasForm ::HandsClothes_var ::temp0 akBaseObject ;@line 90
            JUMPF ::temp0 label7 ;@line 90
            CALLMETHOD AnyEquipped self ::temp0 ::HandsEquipment_var ;@line 91
            JUMPF ::temp0 label8 ;@line 91
            CALLMETHOD UnequipConflicts self ::nonevar ::HandsClothes_var ;@line 92
            JUMP label8 ;@line 92
            label8:
            JUMP label2 ;@line 92
            label7:
            CALLMETHOD HasForm ::FeetClothes_var ::temp0 akBaseObject ;@line 94
            JUMPF ::temp0 label2 ;@line 94
            CALLMETHOD AnyEquipped self ::temp0 ::FeetEquipment_var ;@line 95
            JUMPF ::temp0 label9 ;@line 95
            CALLMETHOD UnequipConflicts self ::nonevar ::FeetClothes_var ;@line 96
            JUMP label9 ;@line 96
            label9:
            JUMP label2 ;@line 96
            label2:
          .endCode
        .endFunction
      .endState
    .endStateTable
  .endObject
.endObjectTable
