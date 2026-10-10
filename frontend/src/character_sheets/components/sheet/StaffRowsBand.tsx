/**
 * Staff edit mode, piece B (#4221): the rows character creation writes, editable on any
 * sheet. Each section shows every slot, filled or blank, and saves through its own staff
 * action; the answer replaces the sheet in the cache. Drawn only in edit mode.
 */

import { useContext, useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import type {
  CharacterSheetStaffRows,
  StaffChoice,
  StaffOption,
  StaffOptions,
  StaffRowAction,
} from '@/character_sheets/api';
import {
  useStaffMagicOptions,
  useStaffOptions,
  useStaffRowMutation,
} from '@/character_sheets/queries';
import { Band } from './primitives';
import { StaffEditContext } from './staffEditContext';

type Run = (request: StaffRowAction, onDone?: () => void) => void;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t pt-3" aria-label={title}>
      <h3 className="refsheet-eyebrow">{title}</h3>
      {children}
    </section>
  );
}

function asItems(options: StaffOption[]) {
  return options.map((option) => ({ value: String(option.id), label: option.name }));
}

function Select({
  label,
  value,
  onChange,
  options,
  blank = '—',
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  blank?: string;
}) {
  return (
    <select
      aria-label={label}
      className="h-9 rounded-md border bg-transparent px-2 text-sm"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{blank}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

const choiceItems = (choices: StaffChoice[]) =>
  choices.map((choice) => ({ value: choice.value, label: choice.label }));

export function StaffRowsBand() {
  const state = useContext(StaffEditContext);
  if (!state) return null;
  return <StaffRows sheetId={state.sheetId} rows={state.stored.rows} />;
}

function StaffRows({ sheetId, rows }: { sheetId: number; rows: CharacterSheetStaffRows }) {
  const { data: options } = useStaffOptions(sheetId, true);
  const mutation = useStaffRowMutation(sheetId);
  const run: Run = (request, onDone) => mutation.mutate(request, { onSuccess: () => onDone?.() });

  return (
    <Band title="Staff edit: rows">
      {!options ? (
        <p className="opacity-70">Loading…</p>
      ) : (
        <div className="flex flex-col gap-4" data-testid="staff-rows-band">
          <StatsEditor rows={rows} options={options} run={run} />
          <SkillsEditor rows={rows} options={options} run={run} />
          <DistinctionsEditor rows={rows} options={options} run={run} />
          <FormEditor rows={rows} options={options} run={run} />
          <OriginEditor rows={rows} options={options} run={run} />
          <MarkingsEditor rows={rows} options={options} run={run} />
          <EnemyEditor options={options} run={run} />
          <IntroductionEditor run={run} />
          {!rows.has_gift && <MagicEditor sheetId={sheetId} run={run} />}
          {!rows.has_vitals && (
            <Section title="Vitals">
              <span>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => run({ path: 'staff-vitals', method: 'POST', body: {} })}
                >
                  Give vitals
                </Button>
              </span>
            </Section>
          )}
        </div>
      )}
    </Band>
  );
}

interface EditorProps {
  rows: CharacterSheetStaffRows;
  options: StaffOptions;
  run: Run;
}

function StatsEditor({ rows, options, run }: EditorProps) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const value = (id: number) =>
    draft[id] ?? (rows.stats[id] !== undefined ? String(rows.stats[id]) : '');
  const changed = Object.entries(draft).filter(([, text]) => text.trim() !== '');
  return (
    <Section title="Stats">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {options.stats.map((stat) => (
          <label key={stat.id} className="flex items-center gap-2 text-sm">
            <span className="w-24 truncate">{stat.name}</span>
            <Input
              aria-label={stat.name}
              type="number"
              min={1}
              max={5}
              className="h-8 w-16"
              value={value(stat.id)}
              onChange={(event) => setDraft({ ...draft, [stat.id]: event.target.value })}
            />
          </label>
        ))}
      </div>
      <span>
        <Button
          type="button"
          size="sm"
          disabled={changed.length === 0}
          onClick={() =>
            run(
              {
                path: 'staff-stats',
                method: 'PATCH',
                body: {
                  stats: Object.fromEntries(changed.map(([id, text]) => [id, Number(text)])),
                },
              },
              () => setDraft({})
            )
          }
        >
          Save stats
        </Button>
      </span>
    </Section>
  );
}

function SkillsEditor({ rows, options, run }: EditorProps) {
  const [skill, setSkill] = useState('');
  const [value, setValue] = useState('');
  const [spec, setSpec] = useState('');
  const [specValue, setSpecValue] = useState('');
  const name = (list: StaffOption[], id: string) =>
    list.find((option) => String(option.id) === id)?.name ?? id;
  return (
    <Section title="Skills">
      <ul className="text-sm">
        {Object.entries(rows.skills).map(([id, points]) => (
          <li key={`s${id}`}>
            {name(options.skills, id)} {points}
          </li>
        ))}
        {Object.entries(rows.specializations).map(([id, points]) => (
          <li key={`p${id}`}>
            {name(options.specializations, id)} {points}
          </li>
        ))}
      </ul>
      <span className="flex flex-wrap items-center gap-2">
        <Combobox
          items={asItems(options.skills)}
          value={skill}
          onValueChange={setSkill}
          placeholder="Skill"
        />
        <Input
          aria-label="Skill value"
          type="number"
          min={0}
          className="h-8 w-20"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
        <Button
          type="button"
          size="sm"
          disabled={!skill || value === ''}
          onClick={() =>
            run(
              {
                path: 'staff-skills',
                method: 'PATCH',
                body: { skills: { [skill]: Number(value) } },
              },
              () => {
                setSkill('');
                setValue('');
              }
            )
          }
        >
          Set skill
        </Button>
      </span>
      <span className="flex flex-wrap items-center gap-2">
        <Combobox
          items={asItems(options.specializations)}
          value={spec}
          onValueChange={setSpec}
          placeholder="Specialization"
        />
        <Input
          aria-label="Specialization value"
          type="number"
          min={0}
          className="h-8 w-20"
          value={specValue}
          onChange={(event) => setSpecValue(event.target.value)}
        />
        <Button
          type="button"
          size="sm"
          disabled={!spec || specValue === ''}
          onClick={() =>
            run(
              {
                path: 'staff-skills',
                method: 'PATCH',
                body: { specializations: { [spec]: Number(specValue) } },
              },
              () => {
                setSpec('');
                setSpecValue('');
              }
            )
          }
        >
          Set specialization
        </Button>
      </span>
    </Section>
  );
}

function DistinctionsEditor({ rows, options, run }: EditorProps) {
  const [adding, setAdding] = useState('');
  return (
    <Section title="Distinctions">
      <ul className="flex flex-col gap-1 text-sm">
        {rows.distinctions.map((held) => (
          <li key={held.id} className="flex flex-wrap items-center gap-2">
            <span>
              {held.name}
              {held.feature ? ` (${held.feature})` : ''}
            </span>
            {held.max_rank > 1 && (
              <Select
                label={`Rank of ${held.name}`}
                value={String(held.rank)}
                options={Array.from({ length: held.max_rank }, (_, i) => ({
                  value: String(i + 1),
                  label: String(i + 1),
                }))}
                onChange={(rank) =>
                  rank &&
                  run({
                    path: 'staff-distinction',
                    method: 'PATCH',
                    body: { character_distinction: held.id, rank: Number(rank) },
                  })
                }
              />
            )}
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                run({
                  path: 'staff-distinction',
                  method: 'PATCH',
                  body: { character_distinction: held.id },
                })
              }
            >
              Remove {held.name}
            </Button>
          </li>
        ))}
      </ul>
      <span className="flex flex-wrap items-center gap-2">
        <Combobox
          items={asItems(options.distinctions)}
          value={adding}
          onValueChange={setAdding}
          placeholder="Distinction"
        />
        <Button
          type="button"
          size="sm"
          disabled={!adding}
          onClick={() =>
            run(
              { path: 'staff-distinctions', method: 'POST', body: { distinction: Number(adding) } },
              () => setAdding('')
            )
          }
        >
          Add distinction
        </Button>
      </span>
    </Section>
  );
}

function FormEditor({ rows, options, run }: EditorProps) {
  if (options.form_traits.length === 0) return null;
  return (
    <Section title="Form">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {options.form_traits.map((trait) => (
          <label key={trait.id} className="flex items-center gap-2 text-sm">
            <span className="w-24 truncate">{trait.name}</span>
            <Select
              label={trait.name}
              value={rows.form[trait.id] !== undefined ? String(rows.form[trait.id]) : ''}
              options={asItems(trait.options)}
              onChange={(option) =>
                option &&
                run({
                  path: 'staff-form',
                  method: 'PATCH',
                  body: { values: { [trait.id]: Number(option) } },
                })
              }
            />
          </label>
        ))}
      </div>
    </Section>
  );
}

function OriginEditor({ rows, options, run }: EditorProps) {
  const [level, setLevel] = useState(rows.class_level ? String(rows.class_level) : '');
  const id = (value: number | null) => (value === null ? '' : String(value));
  return (
    <Section title="Origin and path">
      <label className="flex items-center gap-2 text-sm">
        <span className="w-24">Beginning</span>
        <Select
          label="Beginning"
          value={id(rows.beginnings)}
          options={asItems(options.beginnings)}
          onChange={(value) =>
            value &&
            run({ path: 'staff-beginnings', method: 'PUT', body: { beginnings: Number(value) } })
          }
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <span className="w-24">Path</span>
        {rows.path === null ? (
          <Select
            label="Path"
            value=""
            options={asItems(options.paths)}
            onChange={(value) =>
              value && run({ path: 'staff-path', method: 'PATCH', body: { path: Number(value) } })
            }
          />
        ) : (
          <span>{options.paths.find((path) => path.id === rows.path)?.name}</span>
        )}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <span className="w-24">Level</span>
        <Input
          aria-label="Level"
          type="number"
          min={1}
          max={30}
          className="h-8 w-20"
          value={level}
          onChange={(event) => setLevel(event.target.value)}
        />
        <Button
          type="button"
          size="sm"
          disabled={!level}
          onClick={() =>
            run({ path: 'staff-path', method: 'PATCH', body: { level: Number(level) } })
          }
        >
          Set level
        </Button>
      </label>
      {(['public_being', 'secret_being'] as const).map((which) => (
        <label key={which} className="flex items-center gap-2 text-sm">
          <span className="w-24">{which === 'public_being' ? 'Worships' : 'In secret'}</span>
          <Select
            label={which === 'public_being' ? 'Worships' : 'In secret'}
            value={id(rows[which])}
            options={asItems(options.beings)}
            onChange={(value) =>
              run({
                path: 'staff-worship',
                method: 'PUT',
                body: {
                  public_being: rows.public_being,
                  secret_being: rows.secret_being,
                  [which]: value ? Number(value) : null,
                },
              })
            }
          />
        </label>
      ))}
    </Section>
  );
}

function MarkingsEditor({ rows, options, run }: EditorProps) {
  const [name, setName] = useState('');
  const [region, setRegion] = useState('');
  const [kind, setKind] = useState('');
  return (
    <Section title="Markings">
      <ul className="flex flex-col gap-1 text-sm">
        {rows.markings.map((marking) => (
          <li key={marking.id} className="flex items-center gap-2">
            <span>{marking.name}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                run({
                  path: 'staff-marking-remove',
                  method: 'PATCH',
                  body: { marking: marking.id },
                })
              }
            >
              Remove {marking.name}
            </Button>
          </li>
        ))}
      </ul>
      <span className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="Marking name"
          placeholder="Marking"
          className="h-8 w-48"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Select
          label="Where"
          value={region}
          options={choiceItems(options.marking_regions)}
          onChange={setRegion}
        />
        <Select
          label="Kind"
          value={kind}
          options={choiceItems(options.marking_kinds)}
          onChange={setKind}
        />
        <Button
          type="button"
          size="sm"
          disabled={!name.trim() || !region || !kind}
          onClick={() =>
            run(
              { path: 'staff-markings', method: 'POST', body: { name, body_region: region, kind } },
              () => setName('')
            )
          }
        >
          Add marking
        </Button>
      </span>
    </Section>
  );
}

function EnemyEditor({ options, run }: Pick<EditorProps, 'options' | 'run'>) {
  const [kind, setKind] = useState('');
  const [degree, setDegree] = useState('');
  const [figure, setFigure] = useState('');
  const [tier, setTier] = useState('');
  const [publicLine, setPublicLine] = useState('');
  return (
    <Section title="Enemy">
      <span className="flex flex-wrap items-center gap-2">
        <Select
          label="Enemy kind"
          value={kind}
          options={choiceItems(options.enemy_kinds)}
          onChange={setKind}
        />
        <Select
          label="Degree"
          value={degree}
          options={choiceItems(options.enemy_degrees)}
          onChange={setDegree}
        />
        <Input
          aria-label="Enemy name"
          placeholder="Who"
          className="h-8 w-48"
          value={figure}
          onChange={(event) => setFigure(event.target.value)}
        />
        <Select
          label="Power"
          value={tier}
          options={choiceItems(options.enemy_power_tiers)}
          onChange={setTier}
        />
      </span>
      <Textarea
        aria-label="The line on the sheet"
        rows={2}
        value={publicLine}
        onChange={(event) => setPublicLine(event.target.value)}
      />
      <span>
        <Button
          type="button"
          size="sm"
          disabled={!kind || !degree}
          onClick={() =>
            run({
              path: 'staff-enemy',
              method: 'PUT',
              body: {
                kind,
                degree,
                figure_name: figure,
                power_tier: tier,
                public_line: publicLine,
              },
            })
          }
        >
          Add enemy
        </Button>
      </span>
    </Section>
  );
}

const INTRODUCTIONS = [
  { value: 'first_journal', label: 'First Journal' },
  { value: 'application', label: 'Application' },
  { value: 'whispers', label: 'The Whispers' },
];

function IntroductionEditor({ run }: Pick<EditorProps, 'run'>) {
  const [kind, setKind] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  return (
    <Section title="Introductions">
      <span className="flex flex-wrap items-center gap-2">
        <Select label="Introduction" value={kind} options={INTRODUCTIONS} onChange={setKind} />
        <Input
          aria-label="Title"
          placeholder="Title"
          className="h-8 w-64"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </span>
      <Textarea
        aria-label="Introduction text"
        rows={4}
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />
      <span>
        <Button
          type="button"
          size="sm"
          disabled={!kind || !title.trim() || !body.trim()}
          onClick={() =>
            run(
              { path: 'staff-introductions', method: 'POST', body: { kind, title, body } },
              () => {
                setTitle('');
                setBody('');
              }
            )
          }
        >
          Add introduction
        </Button>
      </span>
    </Section>
  );
}

/**
 * Grant magic (#4224): a giftless sheet's starting magic, picked as CG's magic stage
 * picks it. Each pick narrows the next; the server holds the stage's rules.
 */
function MagicEditor({ sheetId, run }: { sheetId: number; run: Run }) {
  const [tradition, setTradition] = useState('');
  const [gift, setGift] = useState('');
  const [techniques, setTechniques] = useState<number[]>([]);
  const [resonance, setResonance] = useState('');
  const [stat, setStat] = useState('');
  const [skill, setSkill] = useState('');
  const [ritualName, setRitualName] = useState('');
  const [glimpse, setGlimpse] = useState('');
  const { data: options } = useStaffMagicOptions(sheetId, tradition, gift, true);

  const pickTradition = (value: string) => {
    setTradition(value);
    setGift('');
    setTechniques([]);
    setResonance('');
  };
  const pickGift = (value: string) => {
    setGift(value);
    setTechniques([]);
    setResonance('');
  };
  const toggle = (id: number) =>
    setTechniques((held) => (held.includes(id) ? held.filter((t) => t !== id) : [...held, id]));

  const limit = options?.technique_limit ?? 1;
  const ready = tradition && gift && techniques.length > 0 && resonance && stat && skill && options;
  return (
    <Section title="Magic">
      {!options ? (
        <p className="opacity-70">Loading…</p>
      ) : (
        <div className="flex flex-col gap-2" data-testid="staff-magic-editor">
          <div className="flex flex-wrap gap-2">
            <Select
              label="Tradition"
              value={tradition}
              onChange={pickTradition}
              options={asItems(options.traditions)}
            />
            {tradition && (
              <Select
                label="Gift"
                value={gift}
                onChange={pickGift}
                options={asItems(options.gifts)}
              />
            )}
            {gift && (
              <Select
                label="Resonance"
                value={resonance}
                onChange={setResonance}
                options={asItems(options.resonances)}
              />
            )}
          </div>
          {gift && (
            <fieldset className="flex flex-col gap-1">
              <legend className="text-sm">
                Techniques {techniques.length}/{limit}
              </legend>
              {options.techniques.map((technique) => (
                <label key={technique.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={techniques.includes(technique.id)}
                    disabled={!techniques.includes(technique.id) && techniques.length >= limit}
                    onChange={() => toggle(technique.id)}
                  />
                  {technique.name}
                </label>
              ))}
            </fieldset>
          )}
          <div className="flex flex-wrap gap-2">
            <Select
              label="Anima stat"
              value={stat}
              onChange={setStat}
              options={asItems(options.stats)}
            />
            <Select
              label="Anima skill"
              value={skill}
              onChange={setSkill}
              options={asItems(options.skills)}
            />
            <Input
              aria-label="Anima ritual name"
              placeholder="Anima ritual name"
              className="h-9 w-56"
              value={ritualName}
              onChange={(event) => setRitualName(event.target.value)}
            />
          </div>
          <Textarea
            aria-label="Glimpse"
            placeholder="Glimpse"
            rows={3}
            value={glimpse}
            onChange={(event) => setGlimpse(event.target.value)}
          />
          <span>
            <Button
              type="button"
              size="sm"
              disabled={!ready}
              onClick={() =>
                run({
                  path: 'staff-magic',
                  method: 'POST',
                  body: {
                    tradition: Number(tradition),
                    gift: Number(gift),
                    techniques,
                    resonance: Number(resonance),
                    anima_stat: Number(stat),
                    anima_skill: Number(skill),
                    ritual_name: ritualName.trim(),
                    glimpse: glimpse.trim(),
                  },
                })
              }
            >
              Grant magic
            </Button>
          </span>
        </div>
      )}
    </Section>
  );
}
