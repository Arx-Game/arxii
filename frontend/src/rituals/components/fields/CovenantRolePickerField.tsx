/**
 * CovenantRolePickerField — dropdown of CovenantRole lookup rows filtered by covenant_type.
 *
 * Reads `field.depends_on` to find the sibling form field that holds the covenant_type
 * string value. Calls GET /api/covenants/roles/?covenant_type=<value> to retrieve
 * the applicable roles. Renders disabled with a prompt if the dependent field has no value.
 *
 * For Slice B, only the simple sibling-field case is supported. When `depends_on`
 * references a session-level path (e.g. "session.target_covenant.covenant_type"),
 * the parent dialog is expected to resolve it and inject the resolved value into
 * formValues under the depends_on key. TODO: session-path resolution in Task 9.5.
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

type CovenantRole = components['schemas']['CovenantRole'];

async function fetchCovenantRoles(covenantType: string): Promise<CovenantRole[]> {
  const params = new URLSearchParams({ covenant_type: covenantType });
  const res = await apiFetch(`/api/covenants/roles/?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to load covenant roles');
  const data = (await res.json()) as { results?: CovenantRole[] } | CovenantRole[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

export function CovenantRolePickerField({
  field,
  value,
  onChange,
  disabled,
  formValues,
}: FieldProps) {
  const dependsOnKey = field.depends_on ?? '';
  const rawDependentValue = formValues?.[dependsOnKey];
  const covenantType =
    rawDependentValue != null && rawDependentValue !== '' ? String(rawDependentValue) : null;

  const { data, isLoading } = useQuery({
    queryKey: ['covenant-roles', covenantType],
    queryFn: () => fetchCovenantRoles(covenantType!),
    enabled: covenantType != null,
  });

  const roles = data ?? [];

  function handleChange(selectedValue: string) {
    onChange(Number(selectedValue));
  }

  const isDisabled = disabled || covenantType == null || isLoading;

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
              covenantType == null
                ? 'Select a covenant type first'
                : isLoading
                  ? 'Loading roles…'
                  : 'Select a role'
            }
          />
        </SelectTrigger>
        <SelectContent>
          {roles.map((role) => (
            <SelectItem key={role.id} value={String(role.id)}>
              {role.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
