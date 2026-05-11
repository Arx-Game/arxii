/**
 * CovenantPickerField — dropdown of covenants the requesting user is an active member of.
 *
 * Calls GET /api/covenants/covenants/ — scoped server-side to the authenticated user's
 * active memberships. Each option's value is the covenant id (number). Label is the
 * covenant name.
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

type Covenant = components['schemas']['Covenant'];

async function fetchUserCovenants(): Promise<Covenant[]> {
  const res = await apiFetch('/api/covenants/covenants/');
  if (!res.ok) throw new Error('Failed to load covenants');
  const data = (await res.json()) as { results?: Covenant[] } | Covenant[];
  return Array.isArray(data) ? data : (data.results ?? []);
}

export function CovenantPickerField({ field, value, onChange, disabled }: FieldProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['covenants', 'user-memberships'],
    queryFn: fetchUserCovenants,
  });

  const covenants = data ?? [];

  function handleChange(selectedValue: string) {
    onChange(Number(selectedValue));
  }

  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Select
        value={value != null ? String(value) : ''}
        onValueChange={handleChange}
        disabled={disabled || isLoading}
      >
        <SelectTrigger id={field.name}>
          <SelectValue placeholder={isLoading ? 'Loading covenants…' : 'Select a covenant'} />
        </SelectTrigger>
        <SelectContent>
          {covenants.map((covenant) => (
            <SelectItem key={covenant.id} value={String(covenant.id)}>
              {covenant.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
