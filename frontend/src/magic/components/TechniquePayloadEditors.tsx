/**
 * TechniquePayloadEditors — dynamic add/remove row editors for technique payloads.
 *
 * Extracted from TechniqueBuilderForm to stay within the ~250 line limit.
 * Covers three payload types:
 *   - CapabilityGrantRow  (capability_grants)
 *   - DamageProfileRow    (damage_profiles)
 *   - AppliedConditionRow (applied_conditions)
 *
 * Each editor renders a list of rows plus an "Add" button. Rows may be removed
 * individually. Row field changes bubble up via the onUpdate callback.
 */

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Types (pulled from generated schema for lookup lists)
// ---------------------------------------------------------------------------

export type CapabilityType = components['schemas']['CapabilityType'];
export type DamageType = components['schemas']['DamageType'];

interface ConditionOption {
  id: number;
  name: string;
}

// Row shapes mirror TechniqueDesignRequest payload arrays.
export interface CapabilityGrantRow {
  capability_id: number;
  base_value: number;
  intensity_multiplier: number;
}

export interface DamageProfileRow {
  damage_type_id: number | null;
  base_damage: number;
  damage_intensity_multiplier: number;
}

export interface AppliedConditionRow {
  condition_id: number;
  base_severity: number;
  base_duration_rounds: number | null;
}

// ---------------------------------------------------------------------------
// Capability Grants Editor
// ---------------------------------------------------------------------------

interface CapabilityGrantsEditorProps {
  rows: CapabilityGrantRow[];
  capabilities: CapabilityType[];
  disabled?: boolean;
  onChange: (rows: CapabilityGrantRow[]) => void;
}

export function CapabilityGrantsEditor({
  rows,
  capabilities,
  disabled = false,
  onChange,
}: CapabilityGrantsEditorProps) {
  function addRow() {
    if (capabilities.length === 0) return;
    onChange([
      ...rows,
      { capability_id: capabilities[0].id, base_value: 1, intensity_multiplier: 0 },
    ]);
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  function updateRow(index: number, patch: Partial<CapabilityGrantRow>) {
    onChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Capability Grants</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || capabilities.length === 0}
          onClick={addRow}
        >
          + Add
        </Button>
      </div>
      {rows.map((row, i) => (
        <div key={i} className="flex items-end gap-2 rounded-md border p-2">
          <div className="flex-1 space-y-1">
            <Label className="text-xs text-muted-foreground">Capability</Label>
            <Select
              value={String(row.capability_id)}
              onValueChange={(val) => updateRow(i, { capability_id: Number(val) })}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {capabilities.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-20 space-y-1">
            <Label className="text-xs text-muted-foreground">Base value</Label>
            <Input
              type="number"
              min={0}
              className="h-8 text-xs"
              value={row.base_value}
              disabled={disabled}
              onChange={(e) => updateRow(i, { base_value: Number(e.target.value) })}
            />
          </div>
          <div className="w-24 space-y-1">
            <Label className="text-xs text-muted-foreground">×Intensity</Label>
            <Input
              type="number"
              min={0}
              step={0.1}
              className="h-8 text-xs"
              value={row.intensity_multiplier}
              disabled={disabled}
              onChange={(e) => updateRow(i, { intensity_multiplier: Number(e.target.value) })}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-destructive"
            disabled={disabled}
            onClick={() => removeRow(i)}
          >
            ✕
          </Button>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Damage Profiles Editor
// ---------------------------------------------------------------------------

interface DamageProfilesEditorProps {
  rows: DamageProfileRow[];
  damageTypes: DamageType[];
  disabled?: boolean;
  onChange: (rows: DamageProfileRow[]) => void;
}

export function DamageProfilesEditor({
  rows,
  damageTypes,
  disabled = false,
  onChange,
}: DamageProfilesEditorProps) {
  function addRow() {
    onChange([
      ...rows,
      {
        damage_type_id: damageTypes[0]?.id ?? null,
        base_damage: 0,
        damage_intensity_multiplier: 1,
      },
    ]);
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  function updateRow(index: number, patch: Partial<DamageProfileRow>) {
    onChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Damage Profiles</Label>
        <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={addRow}>
          + Add
        </Button>
      </div>
      {rows.map((row, i) => (
        <div key={i} className="flex items-end gap-2 rounded-md border p-2">
          <div className="flex-1 space-y-1">
            <Label className="text-xs text-muted-foreground">Damage type</Label>
            <Select
              value={row.damage_type_id != null ? String(row.damage_type_id) : ''}
              onValueChange={(val) => updateRow(i, { damage_type_id: val ? Number(val) : null })}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="None (untyped)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">None (untyped)</SelectItem>
                {damageTypes.map((dt) => (
                  <SelectItem key={dt.id} value={String(dt.id)}>
                    {dt.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-20 space-y-1">
            <Label className="text-xs text-muted-foreground">Base dmg</Label>
            <Input
              type="number"
              min={0}
              className="h-8 text-xs"
              value={row.base_damage}
              disabled={disabled}
              onChange={(e) => updateRow(i, { base_damage: Number(e.target.value) })}
            />
          </div>
          <div className="w-24 space-y-1">
            <Label className="text-xs text-muted-foreground">×Intensity</Label>
            <Input
              type="number"
              min={0}
              step={0.1}
              className="h-8 text-xs"
              value={row.damage_intensity_multiplier}
              disabled={disabled}
              onChange={(e) =>
                updateRow(i, { damage_intensity_multiplier: Number(e.target.value) })
              }
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-destructive"
            disabled={disabled}
            onClick={() => removeRow(i)}
          >
            ✕
          </Button>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Applied Conditions Editor
// ---------------------------------------------------------------------------

interface AppliedConditionsEditorProps {
  rows: AppliedConditionRow[];
  conditions: ConditionOption[];
  disabled?: boolean;
  onChange: (rows: AppliedConditionRow[]) => void;
}

export function AppliedConditionsEditor({
  rows,
  conditions,
  disabled = false,
  onChange,
}: AppliedConditionsEditorProps) {
  function addRow() {
    if (conditions.length === 0) return;
    onChange([
      ...rows,
      { condition_id: conditions[0].id, base_severity: 1, base_duration_rounds: null },
    ]);
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  function updateRow(index: number, patch: Partial<AppliedConditionRow>) {
    onChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Applied Conditions</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || conditions.length === 0}
          onClick={addRow}
        >
          + Add
        </Button>
      </div>
      {rows.map((row, i) => (
        <div key={i} className="flex items-end gap-2 rounded-md border p-2">
          <div className="flex-1 space-y-1">
            <Label className="text-xs text-muted-foreground">Condition</Label>
            <Select
              value={String(row.condition_id)}
              onValueChange={(val) => updateRow(i, { condition_id: Number(val) })}
              disabled={disabled}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {conditions.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-20 space-y-1">
            <Label className="text-xs text-muted-foreground">Severity</Label>
            <Input
              type="number"
              min={1}
              className="h-8 text-xs"
              value={row.base_severity}
              disabled={disabled}
              onChange={(e) => updateRow(i, { base_severity: Number(e.target.value) })}
            />
          </div>
          <div className="w-24 space-y-1">
            <Label className="text-xs text-muted-foreground">Rounds (blank=∞)</Label>
            <Input
              type="number"
              min={1}
              className="h-8 text-xs"
              value={row.base_duration_rounds ?? ''}
              disabled={disabled}
              placeholder="∞"
              onChange={(e) =>
                updateRow(i, {
                  base_duration_rounds: e.target.value === '' ? null : Number(e.target.value),
                })
              }
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-destructive"
            disabled={disabled}
            onClick={() => removeRow(i)}
          >
            ✕
          </Button>
        </div>
      ))}
    </div>
  );
}
