/**
 * Mirror of backend `world.character_sheets.types` enums.
 */
export enum Gender {
  MALE = 'male',
  FEMALE = 'female',
  NON_BINARY = 'non_binary',
  OTHER = 'other',
}

export const GENDER_LABELS: Record<Gender, string> = {
  [Gender.MALE]: 'Male',
  [Gender.FEMALE]: 'Female',
  [Gender.NON_BINARY]: 'Non-Binary',
  [Gender.OTHER]: 'Other',
};
