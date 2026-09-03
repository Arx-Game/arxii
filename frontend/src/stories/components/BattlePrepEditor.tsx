/**
 * BattlePrepEditor - pre-stage a battle on an ENCOUNTER beat (#3569).
 *
 * BeatFormDialog's kind=encounter mount toggles between OpponentLinesEditor's
 * freeform bestiary rows and this editor (blueprint + party side + unit
 * lines) via `prepMode` - a beat stages either opponent lines or a battle,
 * never both (server-enforced XOR, see BeatSerializer._check_staged_battle_invariants).
 *
 * Draft shape mirrors OpponentLinesEditor's convention: string-typed fields
 * so a half-typed count doesn't fight the input, and the caller owns
 * converting to/from BeatStagedBattleBody (`battlePrepDraftToPayload`) and
 * seeding from a beat being edited (`battlePrepDraftFromBeat`).
 *
 * Region (ruling 8, Fix round 1): `useAreasFlatQuery` (frontend/src/npc_services/queries.ts)
 * lists every Area as a flat {id, name} pair - the same Area model
 * `Battle.region` FKs to - so the region control reuses it rather than
 * duplicating a hook. Region is optional and clearable: `region: ''` means
 * "leave whatever is already there alone" on write (the backend's
 * `_sync_staged_battle` only writes keys present in the payload, so omitting
 * `region` entirely preserves an existing value), while an explicit clear on
 * an existing staged battle sends `region: null` - see
 * `battlePrepDraftToPayload` below for exactly when each applies.
 */

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Combobox } from '@/components/ui/combobox';
import { useBattleMapBlueprintsQuery, useBattleUnitTemplatesQuery } from '@/battles/queries';
import { useAreasFlatQuery } from '@/npc_services/queries';
import type { BeatStagedBattleBody } from '../types';
import type { Beat } from '../types';

/** Draft shape for one staged-battle unit-line row while the form is open. */
export interface BattleUnitLineDraft {
  id?: number;
  template: string;
  side_role: 'attacker' | 'defender';
  place_name: string;
  count: string;
}

/** Draft shape for a beat's staged battle while the form is open. */
export interface BattlePrepDraft {
  id?: number;
  blueprint: string;
  name: string;
  /** '' = none. See the file header note for exactly how this maps to the payload. */
  region: string;
  party_side_role: 'attacker' | 'defender';
  unit_lines: BattleUnitLineDraft[];
}

export interface BattlePrepEditorProps {
  value: BattlePrepDraft;
  onChange: (v: BattlePrepDraft) => void;
  errors: Record<string, unknown> | undefined;
}

export function battlePrepDraftFromBeat(beat: Beat | undefined): BattlePrepDraft {
  const staged = beat?.staged_battle;
  if (!staged) {
    return {
      blueprint: '',
      name: '',
      region: '',
      party_side_role: 'attacker',
      unit_lines: [],
    };
  }
  return {
    id: staged.id,
    blueprint: String(staged.blueprint),
    name: staged.name ?? '',
    region: staged.region != null ? String(staged.region) : '',
    party_side_role: staged.party_side_role ?? 'attacker',
    unit_lines: (staged.unit_lines ?? []).map((line) => ({
      id: line.id,
      template: String(line.template),
      side_role: line.side_role ?? 'attacker',
      place_name: line.place_name ?? '',
      count: String(line.count ?? 1),
    })),
  };
}

export function battlePrepDraftToPayload(draft: BattlePrepDraft): BeatStagedBattleBody {
  // region: '' either means "never set one" (a brand-new draft) or "clear the
  // one this staged battle already has" (editing an existing one, id present).
  // Omitting the key entirely leaves an existing value untouched server-side
  // (see the file header note) - only send an explicit `null` when there is
  // an existing staged battle to actually clear.
  let region: { region?: number | null } = {};
  if (draft.region !== '') {
    region = { region: Number(draft.region) };
  } else if (draft.id !== undefined) {
    region = { region: null };
  }

  return {
    ...(draft.id !== undefined ? { id: draft.id } : {}),
    blueprint: Number(draft.blueprint),
    name: draft.name.trim(),
    ...region,
    party_side_role: draft.party_side_role,
    unit_lines: draft.unit_lines
      .filter((line) => line.template !== '')
      .map((line, index) => ({
        ...(line.id !== undefined ? { id: line.id } : {}),
        template: Number(line.template),
        side_role: line.side_role,
        place_name: line.place_name,
        count: line.count !== '' ? Math.max(1, Number(line.count)) : 1,
        order: index,
      })),
  };
}

/**
 * `errors` is whatever the server returned under `staged_battle` - a nested
 * `{unit_lines: [...]}` dict on a normal validation failure, or a bare
 * string list for a whole-field error (e.g. the ENCOUNTER-only/XOR
 * invariant). Extract each shape defensively; never throw on the other one.
 */
function topLevelErrors(errors: Record<string, unknown> | undefined): string[] {
  if (!errors) return [];
  if (Array.isArray(errors)) return errors.filter((e): e is string => typeof e === 'string');
  return [];
}

function unitLineRowErrors(
  errors: Record<string, unknown> | undefined
): Record<string, string[]>[] | undefined {
  if (!errors || Array.isArray(errors)) return undefined;
  const raw = (errors as { unit_lines?: unknown }).unit_lines;
  return Array.isArray(raw) ? (raw as Record<string, string[]>[]) : undefined;
}

export function BattlePrepEditor({ value, onChange, errors }: BattlePrepEditorProps) {
  const blueprintsQuery = useBattleMapBlueprintsQuery();
  const blueprints = blueprintsQuery.data?.results ?? [];
  const templatesQuery = useBattleUnitTemplatesQuery();
  const templates = templatesQuery.data?.results ?? [];
  const areasQuery = useAreasFlatQuery();
  const areas = areasQuery.data ?? [];

  const blueprintOptions = blueprints.map((bp) => ({ value: String(bp.id), label: bp.name }));
  const selectedBlueprint = blueprints.find((bp) => String(bp.id) === value.blueprint);
  const places = selectedBlueprint?.places ?? [];
  const areaOptions = areas.map((area) => ({ value: String(area.id), label: area.name }));

  const formErrors = topLevelErrors(errors);
  const rowErrors = unitLineRowErrors(errors);

  function update(partial: Partial<BattlePrepDraft>) {
    onChange({ ...value, ...partial });
  }

  function updateUnitLine(index: number, partial: Partial<BattleUnitLineDraft>) {
    onChange({
      ...value,
      unit_lines: value.unit_lines.map((line, i) => (i === index ? { ...line, ...partial } : line)),
    });
  }

  function addUnitLine() {
    onChange({
      ...value,
      unit_lines: [
        ...value.unit_lines,
        { template: '', side_role: 'attacker', place_name: '', count: '1' },
      ],
    });
  }

  function removeUnitLine(index: number) {
    onChange({ ...value, unit_lines: value.unit_lines.filter((_, i) => i !== index) });
  }

  return (
    <div className="space-y-3" data-testid="beat-battle-prep">
      {formErrors.length > 0 && <p className="text-xs text-destructive">{formErrors.join(' ')}</p>}
      <div className="space-y-1.5" data-testid="beat-battle-blueprint">
        <Label>Battle map</Label>
        <Combobox
          items={blueprintOptions}
          value={value.blueprint}
          onValueChange={(val) => update({ blueprint: val })}
          placeholder="Select a battle map…"
          searchPlaceholder="Search battle maps…"
          emptyMessage="No battle maps found."
        />
      </div>
      <div className="space-y-1.5" data-testid="beat-battle-region">
        <Label>Region</Label>
        <Combobox
          items={areaOptions}
          value={value.region}
          onValueChange={(val) => update({ region: val })}
          placeholder="No region"
          searchPlaceholder="Search areas…"
          emptyMessage="No areas found."
          allowDeselect
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="beat-battle-name">Battle name</Label>
        <Input
          id="beat-battle-name"
          data-testid="beat-battle-name"
          placeholder="Blank uses the beat's internal description"
          value={value.name}
          onChange={(e) => update({ name: e.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="beat-battle-party-side">Party side</Label>
        <select
          id="beat-battle-party-side"
          data-testid="beat-battle-party-side"
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          value={value.party_side_role}
          onChange={(e) => update({ party_side_role: e.target.value as 'attacker' | 'defender' })}
        >
          <option value="attacker">Attacker</option>
          <option value="defender">Defender</option>
        </select>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Unit lines</Label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={addUnitLine}
            data-testid="beat-battle-unit-add"
          >
            Add unit line
          </Button>
        </div>
        {value.unit_lines.length === 0 && (
          <p className="text-xs text-muted-foreground">No units staged yet.</p>
        )}
        {value.unit_lines.map((line, index) => {
          const rowError = rowErrors?.[index];
          return (
            <div
              key={line.id ?? `new-${index}`}
              className="grid grid-cols-[1fr_auto_1fr_auto_auto] items-start gap-2 rounded-md border p-2"
              data-testid={`beat-battle-unit-row-${index}`}
            >
              <div className="space-y-1">
                <select
                  className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                  value={line.template}
                  onChange={(e) => updateUnitLine(index, { template: e.target.value })}
                  data-testid={`beat-battle-unit-template-${index}`}
                >
                  <option value="">Select a unit template…</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
                {rowError?.template && (
                  <p className="text-xs text-destructive">{rowError.template.join(' ')}</p>
                )}
              </div>
              <select
                className="rounded-md border bg-background px-2 py-1.5 text-sm"
                value={line.side_role}
                onChange={(e) =>
                  updateUnitLine(index, { side_role: e.target.value as 'attacker' | 'defender' })
                }
                data-testid={`beat-battle-unit-side-${index}`}
              >
                <option value="attacker">Attacker</option>
                <option value="defender">Defender</option>
              </select>
              <select
                className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                value={line.place_name}
                onChange={(e) => updateUnitLine(index, { place_name: e.target.value })}
                data-testid={`beat-battle-unit-place-${index}`}
                disabled={!selectedBlueprint}
              >
                <option value="">No place</option>
                {places.map((place) => (
                  <option key={place.id} value={place.name}>
                    {place.name}
                  </option>
                ))}
              </select>
              <Input
                type="number"
                min={1}
                className="w-16"
                value={line.count}
                onChange={(e) => updateUnitLine(index, { count: e.target.value })}
                data-testid={`beat-battle-unit-count-${index}`}
              />
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => removeUnitLine(index)}
                data-testid={`beat-battle-unit-remove-${index}`}
              >
                Remove
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
