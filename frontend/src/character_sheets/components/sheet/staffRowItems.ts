import type { StaffOption } from '@/character_sheets/api';

/** Staff options as select items (#4221). */
export function asItems(options: StaffOption[]) {
  return options.map((option) => ({ value: String(option.id), label: option.name }));
}
