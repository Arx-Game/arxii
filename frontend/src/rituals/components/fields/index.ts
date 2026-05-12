import type React from 'react';
import type { FieldProps } from '@/rituals/types';
import { TextField } from './TextField';
import { IntField } from './IntField';
import { SelectField } from './SelectField';
import { UnknownFieldFallback } from './UnknownFieldFallback';
import { CharacterSearchField } from './CharacterSearchField';
import { ScenePickerField } from './ScenePickerField';
import { ResonancePickerField } from './ResonancePickerField';
import { RelationshipCapstonePickerField } from './RelationshipCapstonePickerField';
import { CovenantPickerField } from './CovenantPickerField';
import { CovenantRolePickerField } from './CovenantRolePickerField';
import { SoulTetherRolePickerField } from './SoulTetherRolePickerField';

const REGISTRY: Record<string, React.ComponentType<FieldProps>> = {
  text: TextField,
  int: IntField,
  select: SelectField,
  character_search: CharacterSearchField,
  scene_picker: ScenePickerField,
  resonance_picker: ResonancePickerField,
  relationship_capstone_picker: RelationshipCapstonePickerField,
  covenant_picker: CovenantPickerField,
  covenant_role_picker: CovenantRolePickerField,
  soul_tether_role_picker: SoulTetherRolePickerField,
};

export function getFieldComponent(type: string): React.ComponentType<FieldProps> {
  return REGISTRY[type] ?? UnknownFieldFallback;
}

export function registerFieldComponent(type: string, component: React.ComponentType<FieldProps>) {
  REGISTRY[type] = component;
}

export {
  TextField,
  IntField,
  SelectField,
  UnknownFieldFallback,
  CharacterSearchField,
  ScenePickerField,
  ResonancePickerField,
  RelationshipCapstonePickerField,
  CovenantPickerField,
  CovenantRolePickerField,
  SoulTetherRolePickerField,
};
export type { FieldProps };
