.info
.source "V2SInitialWardrobe.psc"
.modifyTime 0
  .compileTime 1791812114
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
            ASSIGN i 0 ;@line 69
            label3:
            CALLMETHOD GetSize items ::temp0 ;@line 70
            COMPARELT ::temp1 i ::temp0 ;@line 70
            JUMPF ::temp1 label0 ;@line 70
            CALLMETHOD GetAt items ::temp2 i ;@line 71
            ASSIGN item ::temp2 ;@line 71
            CAST ::temp1 item ;@line 72
            ASSIGN ::temp1 ::temp1 ;@line 72
            JUMPF ::temp1 label1 ;@line 72
            CALLMETHOD IsEquipped self ::temp1 item ;@line 72
            ASSIGN ::temp1 ::temp1 ;@line 72
            label1:
            JUMPF ::temp1 label2 ;@line 72
            CALLMETHOD UnequipItem self ::nonevar item False True ;@line 73
            CAST ::temp3 item ;@line 74
            STRCAT ::temp3 "VRM2Skyrim: unequipped conflicting garment/equipment " ::temp3 ;@line 74
            CALLSTATIC debug Trace ::nonevar ::temp3 0 ;@line 74
            JUMP label2 ;@line 74
            label2:
            IADD ::temp0 i 1 ;@line 76
            ASSIGN i ::temp0 ;@line 76
            JUMP label3 ;@line 76
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
            CALLMETHOD AnyEquipped self ::temp0 ::BodyEquipment_var 4 ;@line 52
            JUMPF ::temp0 label0 ;@line 52
            CALLMETHOD UnequipConflicts self ::nonevar ::BodyClothes_var ;@line 53
            JUMP label0 ;@line 53
            label0:
            CALLMETHOD AnyEquipped self ::temp0 ::HandsEquipment_var 8 ;@line 55
            JUMPF ::temp0 label1 ;@line 55
            CALLMETHOD UnequipConflicts self ::nonevar ::HandsClothes_var ;@line 56
            JUMP label1 ;@line 56
            label1:
            CALLMETHOD AnyEquipped self ::temp0 ::FeetEquipment_var 128 ;@line 58
            JUMPF ::temp0 label2 ;@line 58
            CALLMETHOD UnequipConflicts self ::nonevar ::FeetClothes_var ;@line 59
            JUMP label2 ;@line 59
            label2:
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
            .local ::temp0 Int
            .local ::temp1 Bool
            .local ::temp2 form
            .local i Int
          .endLocalTable
          .code
            CALLMETHOD GetSize items ::temp0 ;@line 38
            COMPAREGT ::temp1 ::temp0 64 ;@line 38
            JUMPF ::temp1 label0 ;@line 38
            CALLMETHOD GetWornForm self ::temp2 slotMask ;@line 39
            CALLMETHOD HasForm items ::temp1 ::temp2 ;@line 39
            RETURN ::temp1 ;@line 39
            JUMP label0 ;@line 39
            label0:
            ASSIGN i 0 ;@line 41
            label3:
            CALLMETHOD GetSize items ::temp0 ;@line 42
            COMPARELT ::temp1 i ::temp0 ;@line 42
            JUMPF ::temp1 label1 ;@line 42
            CALLMETHOD GetAt items ::temp2 i ;@line 43
            CALLMETHOD IsEquipped self ::temp1 ::temp2 ;@line 43
            JUMPF ::temp1 label2 ;@line 43
            RETURN True ;@line 44
            JUMP label2 ;@line 44
            label2:
            IADD ::temp0 i 1 ;@line 46
            ASSIGN i ::temp0 ;@line 46
            JUMP label3 ;@line 46
            label1:
            RETURN False ;@line 48
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
            CALLMETHOD ResolveCurrentEquipment self ::nonevar ;@line 65
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
            CALLMETHOD IsEquipped self ::temp0 akBaseObject ;@line 82
            NOT ::temp0 ::temp0 ;@line 82
            JUMPF ::temp0 label0 ;@line 82
            RETURN None ;@line 83
            JUMP label0 ;@line 83
            label0:
            CALLMETHOD HasForm ::BodyEquipment_var ::temp0 akBaseObject ;@line 85
            JUMPF ::temp0 label1 ;@line 85
            CALLMETHOD UnequipConflicts self ::nonevar ::BodyClothes_var ;@line 86
            JUMP label1 ;@line 86
            label1:
            CALLMETHOD HasForm ::HandsEquipment_var ::temp0 akBaseObject ;@line 88
            JUMPF ::temp0 label2 ;@line 88
            CALLMETHOD UnequipConflicts self ::nonevar ::HandsClothes_var ;@line 89
            JUMP label2 ;@line 89
            label2:
            CALLMETHOD HasForm ::FeetEquipment_var ::temp0 akBaseObject ;@line 91
            JUMPF ::temp0 label3 ;@line 91
            CALLMETHOD UnequipConflicts self ::nonevar ::FeetClothes_var ;@line 92
            JUMP label3 ;@line 92
            label3:
            CALLMETHOD HasForm ::BodyClothes_var ::temp0 akBaseObject ;@line 94
            JUMPF ::temp0 label4 ;@line 94
            CALLMETHOD AnyEquipped self ::temp0 ::BodyEquipment_var 4 ;@line 95
            JUMPF ::temp0 label5 ;@line 95
            CALLMETHOD UnequipConflicts self ::nonevar ::BodyClothes_var ;@line 96
            JUMP label5 ;@line 96
            label5:
            JUMP label6 ;@line 96
            label4:
            CALLMETHOD HasForm ::HandsClothes_var ::temp0 akBaseObject ;@line 98
            JUMPF ::temp0 label7 ;@line 98
            CALLMETHOD AnyEquipped self ::temp0 ::HandsEquipment_var 8 ;@line 99
            JUMPF ::temp0 label8 ;@line 99
            CALLMETHOD UnequipConflicts self ::nonevar ::HandsClothes_var ;@line 100
            JUMP label8 ;@line 100
            label8:
            JUMP label6 ;@line 100
            label7:
            CALLMETHOD HasForm ::FeetClothes_var ::temp0 akBaseObject ;@line 102
            JUMPF ::temp0 label6 ;@line 102
            CALLMETHOD AnyEquipped self ::temp0 ::FeetEquipment_var 128 ;@line 103
            JUMPF ::temp0 label9 ;@line 103
            CALLMETHOD UnequipConflicts self ::nonevar ::FeetClothes_var ;@line 104
            JUMP label9 ;@line 104
            label9:
            JUMP label6 ;@line 104
            label6:
          .endCode
        .endFunction
      .endState
    .endStateTable
  .endObject
.endObjectTable
