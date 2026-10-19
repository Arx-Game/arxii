/**
 * Powers on the create form (#4418, Screen 1b): path, tradition, gift and techniques,
 * and stat and skill overrides. Held in the form and written after the NPC is minted
 * (see `applyPowers`), so the choices come from the sheet-free power-options read.
 */

import { useQuery } from '@tanstack/react-query';

import { Input } from '@/components/ui/input';
import { fetchNpcPowerOptions, type PowersDraft, type PowerOptions } from './npcFormApi';

type Option = PowerOptions['paths'][number];

const selectClass = 'h-9 rounded-md border bg-transparent px-2 text-sm';

function Pick({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      aria-label={label}
      className={selectClass}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{label}</option>
      {options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.name}
        </option>
      ))}
    </select>
  );
}

function Overrides({
  title,
  options,
  values,
  onChange,
  max,
}: {
  title: string;
  options: Option[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
  max?: number;
}) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="text-xs font-medium text-muted-foreground">{title}</legend>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {options.map((option) => (
          <label key={option.id} className="flex items-center gap-2 text-sm">
            <span className="w-24 truncate">{option.name}</span>
            <Input
              aria-label={`${title}: ${option.name}`}
              type="number"
              min={title === 'Stats' ? 1 : 0}
              max={max}
              className="h-8 w-16"
              value={values[option.id] ?? ''}
              onChange={(event) => onChange({ ...values, [option.id]: event.target.value })}
            />
          </label>
        ))}
      </div>
    </fieldset>
  );
}

interface NpcPowersEditorProps {
  value: PowersDraft;
  onChange: (value: PowersDraft) => void;
}

export function NpcPowersEditor({ value, onChange }: NpcPowersEditorProps) {
  const { data: options } = useQuery({
    queryKey: ['npc-power-options', value.path, value.tradition, value.gift],
    queryFn: () => fetchNpcPowerOptions(value),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const set = (patch: Partial<PowersDraft>) => onChange({ ...value, ...patch });
  const toggle = (id: number) =>
    set({
      techniques: value.techniques.includes(id)
        ? value.techniques.filter((held) => held !== id)
        : [...value.techniques, id],
    });
  const started = Boolean(value.tradition || value.gift);
  const limit = options?.technique_limit ?? 1;
  const missing = [
    !value.tradition && 'tradition',
    !value.gift && 'gift',
    value.techniques.length === 0 && 'a technique',
    !value.resonance && 'resonance',
    !value.animaStat && 'anima stat',
    !value.animaSkill && 'anima skill',
  ].filter(Boolean) as string[];

  if (!options) return <p className="text-sm text-muted-foreground">Loading…</p>;
  return (
    <div className="flex flex-col gap-4" data-testid="npc-powers-editor">
      <div className="flex flex-wrap items-center gap-2">
        <Pick
          label="Path"
          value={value.path}
          options={options.paths}
          onChange={(path) => set({ path })}
        />
        <Input
          aria-label="Path level"
          type="number"
          min={1}
          className="h-9 w-24"
          placeholder="Level"
          value={value.level}
          onChange={(event) => set({ level: event.target.value })}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Pick
          label="Tradition"
          value={value.tradition}
          options={options.traditions}
          onChange={(tradition) => set({ tradition, gift: '', techniques: [], resonance: '' })}
        />
        {value.tradition && (
          <Pick
            label="Gift"
            value={value.gift}
            options={options.gifts}
            onChange={(gift) => set({ gift, techniques: [], resonance: '' })}
          />
        )}
        {value.gift && (
          <Pick
            label="Resonance"
            value={value.resonance}
            options={options.resonances}
            onChange={(resonance) => set({ resonance })}
          />
        )}
      </div>
      {value.gift && (
        <fieldset className="flex flex-col gap-1">
          <legend className="text-xs font-medium text-muted-foreground">
            Techniques {value.techniques.length}/{limit}
          </legend>
          {options.techniques.map((technique) => (
            <label key={technique.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.techniques.includes(technique.id)}
                disabled={
                  !value.techniques.includes(technique.id) && value.techniques.length >= limit
                }
                onChange={() => toggle(technique.id)}
              />
              {technique.name}
            </label>
          ))}
        </fieldset>
      )}
      {started && (
        <div className="flex flex-wrap items-center gap-2">
          <Pick
            label="Anima stat"
            value={value.animaStat}
            options={options.stats}
            onChange={(animaStat) => set({ animaStat })}
          />
          <Pick
            label="Anima skill"
            value={value.animaSkill}
            options={options.skills}
            onChange={(animaSkill) => set({ animaSkill })}
          />
        </div>
      )}
      {started && missing.length > 0 && (
        <p data-testid="powers-magic-incomplete" className="text-xs text-muted-foreground">
          Magic still needs: {missing.join(', ')}.
        </p>
      )}

      <Overrides
        title="Stats"
        options={options.all_stats}
        values={value.stats}
        max={5}
        onChange={(stats) => set({ stats })}
      />
      <Overrides
        title="Skills"
        options={options.all_skills}
        values={value.skills}
        onChange={(skills) => set({ skills })}
      />
    </div>
  );
}
