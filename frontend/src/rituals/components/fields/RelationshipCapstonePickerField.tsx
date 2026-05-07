/**
 * RelationshipCapstonePickerField — dropdown of the caller's RelationshipCapstone rows.
 *
 * Calls GET /api/relationships/relationship-capstones/ scoped to the authenticated user.
 * Accepts an optional ?other_character_sheet_id= filter via formValues.sineater_sheet_id.
 *
 * If formValues.sineater_sheet_id is not set, the dropdown is disabled and shows a
 * placeholder prompting the user to select a Sineater first.
 *
 * Each option's value is the RelationshipCapstone id. Label is the capstone title.
 *
 * Cross-field dependency: reads formValues?.sineater_sheet_id to filter results.
 * FieldProps was extended with formValues for this purpose (see types.ts).
 */

import { useQuery } from '@tanstack/react-query';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import type { FieldProps } from '@/rituals/types';

type RelationshipCapstone = components['schemas']['RelationshipCapstone'];

async function fetchRelationshipCapstones(
  otherCharacterSheetId?: number
): Promise<RelationshipCapstone[]> {
  const params = new URLSearchParams();
  if (otherCharacterSheetId != null) {
    params.set('other_character_sheet_id', String(otherCharacterSheetId));
  }
  const qs = params.toString() ? `?${params.toString()}` : '';
  const res = await apiFetch(`/api/relationships/relationship-capstones/${qs}`);
  if (!res.ok) throw new Error('Failed to load relationship capstones');
  const data = (await res.json()) as { results?: RelationshipCapstone[] } | RelationshipCapstone[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

export function RelationshipCapstonePickerField({
  field,
  value,
  onChange,
  disabled,
  formValues,
}: FieldProps) {
  const sineaterSheetId =
    formValues?.sineater_sheet_id != null
      ? Number(formValues.sineater_sheet_id) || undefined
      : undefined;

  const hasSineater = sineaterSheetId != null;

  const { data, isLoading } = useQuery({
    queryKey: ['relationship-capstones', sineaterSheetId],
    queryFn: () => fetchRelationshipCapstones(sineaterSheetId),
    enabled: hasSineater,
  });

  const capstones = data ?? [];

  function handleChange(selectedValue: string) {
    onChange(Number(selectedValue));
  }

  const isDisabled = disabled || !hasSineater || isLoading;

  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Select
        value={value != null ? String(value) : ''}
        onValueChange={handleChange}
        disabled={isDisabled}
      >
        <SelectTrigger id={field.name}>
          <SelectValue
            placeholder={
              !hasSineater
                ? 'Select a Sineater first'
                : isLoading
                  ? 'Loading capstones…'
                  : 'Select a capstone'
            }
          />
        </SelectTrigger>
        <SelectContent>
          {capstones.map((capstone) => (
            <SelectItem key={capstone.id} value={String(capstone.id)}>
              {capstone.title}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
