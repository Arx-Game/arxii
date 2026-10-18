/**
 * NpcForm - the GM's new-NPC form (#4418, Screens 1a and 1b).
 *
 * One form, two densities. Quick is a name, a "Copy from" and a description; Detailed
 * opens every section: who they are, description, background and drives, powers, who
 * they favor and oppose, what works on them, notes for whoever plays them, and owner
 * and lending. Every section is optional and every section can be copied from another
 * NPC or a template; whatever is left blank comes from "Start from" or stays empty.
 *
 * "Create NPC" mints through `mint_story_npc` and then writes only the sections the GM
 * filled in or copied (see `createNpc`). The portrait and the powers editors need the
 * NPC to exist, so they open on the created NPC: the portrait through the gallery's
 * add-a-look flow, the powers through the sheet's edit mode.
 */

import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { AddLookFlow } from '@/character_sheets/components/sheet/gallery/AddLookFlow';
import type { StaffChoiceField, StaffEditBody } from '@/character_sheets/api';
import { useStaffChoiceOptions } from '@/character_sheets/queries';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useActiveCharacterId } from '@/gm-adjudication/useActiveCharacterId';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { NpcPreferenceEditor } from './NpcPreferenceEditor';
import { NpcRegardEditor } from './NpcRegardEditor';
import { NpcSectionCopy } from './NpcSectionCopy';
import {
  copyNpcAsNew,
  createNpc,
  fetchNpcTemplates,
  fetchSheetIdForEntry,
  fetchStatlinePresets,
  type BorrowAudience,
  type LendPolicy,
  type NpcCopySource,
  type NpcFormDraft,
  type NpcSection,
  type NpcSettingsPatch,
  type PreferenceLine,
  type RegardLine,
} from './npcFormApi';

export type NpcFormMode = 'quick' | 'detailed';

const LEND_POLICIES: { value: LendPolicy; label: string }[] = [
  { value: 'not_lent', label: 'Only me' },
  { value: 'on_request', label: 'Me, and anyone I lend them to' },
  { value: 'without_asking', label: 'Anyone who borrows them, without asking' },
];
const BORROW_AUDIENCES: { value: BorrowAudience; label: string }[] = [
  { value: 'gms', label: 'Any GM' },
  { value: 'gms_and_guides', label: 'Any GM or Guide' },
];
/** `StoryNPCSettings`' column defaults: what a new NPC has unless the GM changes it. */
const DEFAULT_SETTINGS = {
  listed_on_npc_roster: false,
  lend_policy: 'not_lent' as LendPolicy,
  borrow_audience: 'gms' as BorrowAudience,
};

const QUICK_SECTIONS = [
  'Who they are',
  'Background',
  'Powers',
  'Favors and opposes',
  'What works on them',
  'Notes',
  'Owner and lending',
];

const selectClass = 'h-9 w-full rounded-md border bg-transparent px-2 text-sm';

function initials(name: string): string {
  const letters = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '');
  return letters.join('') || '?';
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={htmlFor} className="text-xs text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}

/** A field with no write path: shown, never edited. */
function ReadOnlyField({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="flex h-9 items-center text-sm text-muted-foreground">{'—'}</span>
    </div>
  );
}

function FormSection({
  title,
  copy,
  children,
}: {
  title: string;
  copy?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3 border-t pt-4" aria-label={title}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-base">{title}</h3>
        {copy}
      </div>
      {children}
    </section>
  );
}

function ChoiceField({
  field,
  label,
  value,
  onChange,
}: {
  field: StaffChoiceField;
  label: string;
  value: number | null | undefined;
  onChange: (value: number | null) => void;
}) {
  const [opened, setOpened] = useState(false);
  const { data: items = [], isLoading } = useStaffChoiceOptions(field, opened);
  return (
    <Field label={label}>
      <span
        aria-label={label}
        onPointerDownCapture={() => setOpened(true)}
        onFocusCapture={() => setOpened(true)}
      >
        <Combobox
          items={items}
          value={value === null || value === undefined ? '' : String(value)}
          onValueChange={(next) => onChange(next === '' ? null : Number(next))}
          placeholder={isLoading ? 'Loading…' : label}
          allowDeselect
        />
      </span>
    </Field>
  );
}

interface CreatedNpc {
  entryId: number;
  name: string;
}

export function NpcForm({ mode: initialMode = 'quick' }: { mode?: NpcFormMode }) {
  const queryClient = useQueryClient();
  const actorId = useActiveCharacterId();
  const [mode, setMode] = useState<NpcFormMode>(initialMode);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [preset, setPreset] = useState('');
  const [startFrom, setStartFrom] = useState<number | null>(null);
  const [sectionCopies, setSectionCopies] = useState<Partial<Record<NpcSection, number>>>({});
  const [sheet, setSheet] = useState<StaffEditBody>({});
  const [regard, setRegard] = useState<RegardLine[]>([]);
  const [preferences, setPreferences] = useState<PreferenceLine[]>([]);
  const [settings, setSettings] = useState<NpcSettingsPatch>({});
  const [created, setCreated] = useState<CreatedNpc | null>(null);
  const [templateName, setTemplateName] = useState<string | null>(null);

  const { data: templates = [] } = useQuery({
    queryKey: ['npc-templates'],
    queryFn: fetchNpcTemplates,
    retry: false,
  });
  const { data: presets = [] } = useQuery({
    queryKey: ['npc-statline-presets'],
    queryFn: fetchStatlinePresets,
    enabled: mode === 'detailed',
    retry: false,
  });
  const { data: myEntries = [] } = useMyRosterEntriesQuery();

  const sources: NpcCopySource[] = [
    ...templates.map((row) => ({ id: row.id, label: `${row.name} (template)` })),
    ...myEntries
      .filter((entry) => entry.roster_type === 'NPC' && !templates.some((t) => t.id === entry.id))
      .map((entry) => ({ id: entry.id, label: entry.name })),
  ];

  const setSheetField = <K extends keyof StaffEditBody>(key: K, value: StaffEditBody[K] | '') => {
    setSheet((current) => {
      const next = { ...current };
      if (value === '' || value === null || value === undefined) delete next[key];
      else next[key] = value as StaffEditBody[K];
      return next;
    });
  };
  const setNumber = (key: 'ic_birth_year' | 'true_height_inches' | 'social_rank', raw: string) =>
    setSheetField(key, raw.trim() === '' ? '' : Number(raw));
  const setSetting = <K extends keyof NpcSettingsPatch>(key: K, value: NpcSettingsPatch[K]) => {
    setSettings((current) => {
      const next = { ...current };
      const isDefault =
        key === 'notes_for_player'
          ? value === ''
          : DEFAULT_SETTINGS[key as keyof typeof DEFAULT_SETTINGS] === value;
      if (isDefault) delete next[key];
      else next[key] = value;
      return next;
    });
  };
  const setSectionCopy = (section: NpcSection, source: number | null) =>
    setSectionCopies((current) => {
      const next = { ...current };
      if (source === null) delete next[section];
      else next[section] = source;
      return next;
    });

  const draft = (): NpcFormDraft => ({
    name,
    description,
    preset,
    startFrom,
    sectionCopies,
    sheet,
    regard,
    preferences,
    settings,
  });

  const afterCreate = (entryId: number) => {
    setCreated({ entryId, name: name.trim() });
    void queryClient.invalidateQueries({ queryKey: ['my-roster-entries'] });
  };

  const create = useMutation({
    mutationFn: () => {
      if (actorId === null) {
        return Promise.reject(new Error('Puppet a character to create an NPC.'));
      }
      return createNpc(actorId, draft());
    },
    onSuccess: afterCreate,
  });

  const saveTemplate = useMutation({
    mutationFn: async (asName: string) => {
      let entryId = created?.entryId ?? null;
      if (entryId === null) {
        if (actorId === null) throw new Error('Puppet a character to create an NPC.');
        entryId = await createNpc(actorId, draft());
        afterCreate(entryId);
      }
      await copyNpcAsNew(entryId, asName, true);
    },
    onSuccess: () => {
      setTemplateName(null);
      void queryClient.invalidateQueries({ queryKey: ['npc-templates'] });
    },
  });

  const reset = () => {
    setName('');
    setDescription('');
    setPreset('');
    setStartFrom(null);
    setSectionCopies({});
    setSheet({});
    setRegard([]);
    setPreferences([]);
    setSettings({});
    setCreated(null);
    setTemplateName(null);
    create.reset();
    saveTemplate.reset();
  };

  const busy = create.isPending || saveTemplate.isPending;
  const error = (create.error ?? saveTemplate.error) as Error | null;
  let submitLabel = mode === 'quick' ? 'Create and add to scene' : 'Create NPC';
  if (create.isPending) submitLabel = 'Creating…';
  const lendPolicy = settings.lend_policy ?? DEFAULT_SETTINGS.lend_policy;
  const copyFor = (section: NpcSection, title: string) => (
    <NpcSectionCopy
      section={title}
      sources={sources}
      value={sectionCopies[section] ?? null}
      onChange={(source) => setSectionCopy(section, source)}
    />
  );

  const templateRow =
    templateName !== null ? (
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="Template name"
          className="max-w-xs"
          value={templateName}
          onChange={(event) => setTemplateName(event.target.value)}
        />
        <Button
          type="button"
          size="sm"
          disabled={templateName.trim() === '' || busy}
          onClick={() => saveTemplate.mutate(templateName.trim())}
        >
          {saveTemplate.isPending ? 'Saving…' : 'Save template'}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setTemplateName(null)}>
          Cancel
        </Button>
      </div>
    ) : null;

  if (created) {
    return (
      <CreatedNpcPanel
        created={created}
        templateRow={templateRow}
        templateSaved={saveTemplate.isSuccess}
        error={error}
        onSaveAsTemplate={() => setTemplateName(`${created.name} template`)}
        onNew={reset}
      />
    );
  }

  return (
    <form
      className="flex flex-col gap-4"
      aria-label="New NPC"
      onSubmit={(event) => {
        event.preventDefault();
        create.mutate();
      }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="flex-1 font-display text-lg">New NPC</h2>
        <div className="inline-flex rounded-md border p-0.5" role="group" aria-label="Form">
          {(['quick', 'detailed'] as const).map((option) => (
            <Button
              key={option}
              type="button"
              size="sm"
              variant={mode === option ? 'secondary' : 'ghost'}
              aria-pressed={mode === option}
              onClick={() => setMode(option)}
            >
              {option === 'quick' ? 'Quick' : 'Detailed'}
            </Button>
          ))}
        </div>
      </div>

      {mode === 'quick' ? (
        <>
          <div className="flex flex-wrap items-start gap-4">
            <Avatar className="h-16 w-16">
              <AvatarFallback>{initials(name)}</AvatarFallback>
            </Avatar>
            <div className="grid min-w-[14rem] flex-1 gap-3 sm:grid-cols-2">
              <Field label="Name" htmlFor="npc-name">
                <Input id="npc-name" value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="Copy from" htmlFor="npc-start-from">
                <select
                  id="npc-start-from"
                  className={selectClass}
                  value={startFrom ?? ''}
                  onChange={(e) =>
                    setStartFrom(e.target.value === '' ? null : Number(e.target.value))
                  }
                >
                  <option value="">{'—'}</option>
                  {sources.map((source) => (
                    <option key={source.id} value={source.id}>
                      {source.label}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </div>
          <Field label="Description" htmlFor="npc-description">
            <Textarea
              id="npc-description"
              rows={8}
              className="resize-y"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
          <div className="flex flex-wrap gap-2">
            {QUICK_SECTIONS.map((section) => (
              <Button
                key={section}
                type="button"
                size="sm"
                variant="outline"
                className="border-dashed"
                onClick={() => setMode('detailed')}
              >
                + {section}
              </Button>
            ))}
          </div>
        </>
      ) : (
        <>
          <FormSection title="Start from">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Copy an NPC or template" htmlFor="npc-start-from">
                <select
                  id="npc-start-from"
                  className={selectClass}
                  value={startFrom ?? ''}
                  onChange={(e) =>
                    setStartFrom(e.target.value === '' ? null : Number(e.target.value))
                  }
                >
                  <option value="">{'—'}</option>
                  {sources.map((source) => (
                    <option key={source.id} value={source.id}>
                      {source.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Stat block" htmlFor="npc-preset">
                <select
                  id="npc-preset"
                  className={selectClass}
                  value={preset}
                  onChange={(e) => setPreset(e.target.value)}
                >
                  <option value="">{'—'}</option>
                  {presets.map((option) => (
                    <option key={option.id} value={option.name}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </FormSection>

          <FormSection title="Who they are" copy={copyFor('identity', 'Who they are')}>
            <div className="flex flex-wrap items-start gap-4">
              <Avatar className="h-20 w-20">
                <AvatarFallback>{initials(name)}</AvatarFallback>
              </Avatar>
              <div className="grid min-w-[14rem] flex-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="Name" htmlFor="npc-name">
                  <Input id="npc-name" value={name} onChange={(e) => setName(e.target.value)} />
                </Field>
                <ReadOnlyField label="Title" />
                <ChoiceField
                  field="gender"
                  label="Gender"
                  value={sheet.gender}
                  onChange={(v) => setSheetField('gender', v)}
                />
                <ChoiceField
                  field="pronouns"
                  label="Pronouns"
                  value={sheet.pronouns}
                  onChange={(v) => setSheetField('pronouns', v)}
                />
                <ChoiceField
                  field="species"
                  label="Species"
                  value={sheet.species}
                  onChange={(v) => setSheetField('species', v)}
                />
                <Field label="Born (IC year)" htmlFor="npc-born">
                  <Input
                    id="npc-born"
                    type="number"
                    value={sheet.ic_birth_year ?? ''}
                    onChange={(e) => setNumber('ic_birth_year', e.target.value)}
                  />
                </Field>
                <Field label="Height (inches)" htmlFor="npc-height">
                  <Input
                    id="npc-height"
                    type="number"
                    min={12}
                    max={600}
                    value={sheet.true_height_inches ?? ''}
                    onChange={(e) => setNumber('true_height_inches', e.target.value)}
                  />
                </Field>
                <ChoiceField
                  field="build"
                  label="Build"
                  value={sheet.build}
                  onChange={(v) => setSheetField('build', v)}
                />
                <Field label="Vocation" htmlFor="npc-vocation">
                  <Input
                    id="npc-vocation"
                    value={sheet.vocation ?? ''}
                    onChange={(e) => setSheetField('vocation', e.target.value)}
                  />
                </Field>
                <Field label="Social rank" htmlFor="npc-social-rank">
                  <Input
                    id="npc-social-rank"
                    type="number"
                    min={1}
                    max={20}
                    value={sheet.social_rank ?? ''}
                    onChange={(e) => setNumber('social_rank', e.target.value)}
                  />
                </Field>
                <ChoiceField
                  field="family"
                  label="Family"
                  value={sheet.family}
                  onChange={(v) => setSheetField('family', v)}
                />
                <ReadOnlyField label="Languages" />
              </div>
            </div>
          </FormSection>

          <FormSection title="Description" copy={copyFor('description', 'Description')}>
            <Textarea
              aria-label="Description"
              rows={8}
              className="resize-y"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </FormSection>

          <FormSection
            title="Background and drives"
            copy={copyFor('background', 'Background and drives')}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              {(
                [
                  ['concept', 'Concept'],
                  ['protect', 'Protects'],
                  ['fear', 'Fears'],
                  ['never_do', 'Would never'],
                ] as const
              ).map(([key, label]) => (
                <Field key={key} label={label} htmlFor={`npc-${key}`}>
                  <Textarea
                    id={`npc-${key}`}
                    rows={8}
                    className="resize-y"
                    value={sheet[key] ?? ''}
                    onChange={(e) => setSheetField(key, e.target.value)}
                  />
                </Field>
              ))}
            </div>
            <Field label="Background" htmlFor="npc-background">
              <Textarea
                id="npc-background"
                rows={10}
                className="resize-y"
                value={sheet.background ?? ''}
                onChange={(e) => setSheetField('background', e.target.value)}
              />
            </Field>
          </FormSection>

          <FormSection title="Powers" copy={copyFor('powers', 'Powers')}>
            <div className="grid gap-3 sm:grid-cols-3">
              <ReadOnlyField label="Gift" />
              <ReadOnlyField label="Techniques" />
              <ReadOnlyField label="Stat overrides" />
            </div>
          </FormSection>

          <FormSection
            title="Who they favor and oppose"
            copy={copyFor('regard', 'Who they favor and oppose')}
          >
            <NpcRegardEditor lines={regard} onChange={setRegard} />
          </FormSection>

          <FormSection
            title="What works on them"
            copy={copyFor('preferences', 'What works on them')}
          >
            <NpcPreferenceEditor traits={[]} lines={preferences} onChange={setPreferences} />
          </FormSection>

          <FormSection title="Notes for whoever plays them">
            <Textarea
              aria-label="Notes for whoever plays them"
              rows={10}
              className="resize-y"
              value={settings.notes_for_player ?? ''}
              onChange={(e) => setSetting('notes_for_player', e.target.value)}
            />
          </FormSection>

          <FormSection title="Owner and lending">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Owner">
                <span className="flex h-9 items-center text-sm">You</span>
              </Field>
              <Field label="NPC roster">
                <label className="flex h-9 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={settings.listed_on_npc_roster ?? DEFAULT_SETTINGS.listed_on_npc_roster}
                    onChange={(e) => setSetting('listed_on_npc_roster', e.target.checked)}
                  />
                  List on the NPC roster
                </label>
              </Field>
              <Field label={`Who may play ${name.trim() || 'them'}`} htmlFor="npc-lend-policy">
                <select
                  id="npc-lend-policy"
                  className={selectClass}
                  value={lendPolicy}
                  onChange={(e) => setSetting('lend_policy', e.target.value as LendPolicy)}
                >
                  {LEND_POLICIES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Who may ask to borrow" htmlFor="npc-borrow-audience">
                <select
                  id="npc-borrow-audience"
                  className={selectClass}
                  disabled={lendPolicy === 'not_lent'}
                  value={settings.borrow_audience ?? DEFAULT_SETTINGS.borrow_audience}
                  onChange={(e) => setSetting('borrow_audience', e.target.value as BorrowAudience)}
                >
                  {BORROW_AUDIENCES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </FormSection>
        </>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error.message}
        </p>
      )}
      {templateRow}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={name.trim() === '' || busy}>
          {submitLabel}
        </Button>
        {mode === 'detailed' && (
          <Button
            type="button"
            variant="outline"
            disabled={name.trim() === '' || busy || templateName !== null}
            onClick={() => setTemplateName(`${name.trim()} template`)}
          >
            Save as template
          </Button>
        )}
      </div>
    </form>
  );
}

function CreatedNpcPanel({
  created,
  templateRow,
  templateSaved,
  error,
  onSaveAsTemplate,
  onNew,
}: {
  created: CreatedNpc;
  templateRow: ReactNode;
  templateSaved: boolean;
  error: Error | null;
  onSaveAsTemplate: () => void;
  onNew: () => void;
}) {
  const [addingPortrait, setAddingPortrait] = useState(false);
  const { data: sheetId } = useQuery({
    queryKey: ['roster-entry-sheet', created.entryId],
    queryFn: () => fetchSheetIdForEntry(created.entryId),
    enabled: addingPortrait,
    staleTime: Infinity,
  });
  return (
    <div className="flex flex-col gap-4" aria-label={created.name} role="region">
      <div className="flex flex-wrap items-center gap-3">
        <Avatar className="h-16 w-16">
          <AvatarFallback>{initials(created.name)}</AvatarFallback>
        </Avatar>
        <h2 className="flex-1 font-display text-lg">{created.name}</h2>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error.message}
        </p>
      )}
      {templateSaved && <p className="text-sm">Saved as a template.</p>}
      {templateRow}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => setAddingPortrait(true)}>
          Add portrait
        </Button>
        <Button asChild variant="outline">
          <Link to={`/characters/${created.entryId}`}>Open sheet</Link>
        </Button>
        {!templateSaved && (
          <Button type="button" variant="outline" onClick={onSaveAsTemplate}>
            Save as template
          </Button>
        )}
        <Button type="button" onClick={onNew}>
          New NPC
        </Button>
      </div>
      {sheetId !== undefined && (
        <AddLookFlow
          open={addingPortrait}
          entryId={created.entryId}
          sheetId={sheetId}
          ink="ember"
          onClose={() => setAddingPortrait(false)}
        />
      )}
    </div>
  );
}
