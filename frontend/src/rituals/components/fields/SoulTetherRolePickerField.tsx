/**
 * SoulTetherRolePickerField — two-option picker for the Soul Tether role.
 *
 * Renders a select with SINEATER and SINNER options matching the backend
 * SoulTetherRole TextChoices (world/magic/constants.py). Value is the string
 * constant ("SINEATER" or "SINNER"); onChange is called with the string value.
 */

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import type { FieldProps } from '@/rituals/types';

const SOUL_TETHER_ROLES = [
  { value: 'SINEATER', label: 'Sineater' },
  { value: 'SINNER', label: 'Sinner' },
] as const;

export function SoulTetherRolePickerField({ field, value, onChange, disabled }: FieldProps) {
  function handleChange(selectedValue: string) {
    onChange(selectedValue);
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Select
        value={value != null ? String(value) : ''}
        onValueChange={handleChange}
        disabled={disabled}
      >
        <SelectTrigger id={field.name}>
          <SelectValue placeholder="Select a role" />
        </SelectTrigger>
        <SelectContent>
          {SOUL_TETHER_ROLES.map((role) => (
            <SelectItem key={role.value} value={role.value}>
              {role.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
