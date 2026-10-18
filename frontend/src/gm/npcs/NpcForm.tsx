/**
 * NpcForm - the GM's new-NPC form (#4418, Screens 1a and 1b).
 *
 * One form, two densities. Quick is a name, a "Copy from" and a description, with the
 * other sections as chips that open inline; Detailed opens every section: who they are,
 * description, background and drives, powers, who they favor and oppose, what works on
 * them, notes for whoever plays them, and owner and lending. Every section is optional
 * and every section can be copied from another NPC or a template; whatever is left
 * blank comes from "Start from" or stays empty. Only the sections on screen are sent:
 * Quick never sends a section the GM filled in Detailed and then closed by switching.
 *
 * "Create NPC" mints through `mint_story_npc` and then writes the copies and the filled
 * sections (see `createNpc`). The minted id is kept the moment the mint succeeds, so a
 * failed later step is retried without a second mint. The portrait and the powers
 * editors need the NPC to exist, so they open on the created NPC.
 */

import { useState, type KeyboardEvent, type ReactNode } from 'react';
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
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useBrowsingIdentity } from '@/roster/useBrowsingIdentity';
import { NpcPowersPanel } from './NpcPowersPanel';
import { NpcPreferenceEditor } from './NpcPreferenceEditor';
import { NpcRegardEditor } from './NpcRegardEditor';
import { NpcSectionCopy } from './NpcSectionCopy';
import {
  BACKGROUND_KEYS,
  IDENTITY_KEYS,
  NpcStepError,
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

/** The sections Quick folds into chips; Detailed shows them all. */
type FoldedSection =
  | 'identity'
  | 'background'
  | 'powers'
  | 'regard'
  | 'preferences'
  | 'notes'
  | 'lending';

const QUICK_CHIPS: { section: FoldedSection; label: string }[] = [
  { section: 'identity', label: 'Who they are' },
  { section: 'background', label: 'Background' },
  { section: 'powers', label: 'Powers' },
  { section: 'regard', label: 'Favors and opposes' },
  { section: 'preferences', label: 'What works on them' },
  { section: 'notes', label: 'Notes' },
  { section: 'lending', label: 'Owner and lending' },
];

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

/** Enter in a one-line input never submits the whole form; sub-editors handle their own. */
function holdEnter(event: KeyboardEvent<HTMLFormElement>) {
  const target = event.target as HTMLElement;
  if (event.key === 'Enter' && target.tagName === 'INPUT') event.preventDefault();
}

function failureText(error: Error, name: string): string {
  if (error instanceof NpcStepError) {
    return `${name} was created; ${error.step} failed. Try again.`;
  }
  return error.message;
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

function FormSection({
  title,
  copy,
  children,
}: {
  title: string;
  copy?: ReactNode;
  children?: ReactNode;
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

/** An identity choice, from the same lookup lists the staff edit mode uses. */
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
  // The wrapping label names the combobox trigger.
  return (
    <label
      className="flex flex-col gap-1"
      onPointerDownCapture={() => setOpened(true)}
      onFocusCapture={() => setOpened(true)}
    >
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Combobox
        items={items}
        value={value === null || value === undefined ? '' : String(value)}
        onValueChange={(next) => onChange(next === '' ? null : Number(next))}
        placeholder={isLoading ? 'Loading…' : label}
        allowDeselect
      />
    </label>
  );
}

interface CreatedNpc {
  entryId: number;
  name: string;
}

export function NpcForm({ mode: initialMode = 'quick' }: { mode?: NpcFormMode }) {
  const queryClient = useQueryClient();
  const identity = useBrowsingIdentity();
  const actorId = identity.entry?.character_id ?? null;
  const [mode, setMode] = useState<NpcFormMode>(initialMode);
  const [expanded, setExpanded] = useState<Set<FoldedSection>>(new Set());

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [preset, setPreset] = useState('');
  const [startFrom, setStartFrom] = useState<number | null>(null);
  const [sectionCopies, setSectionCopies] = useState<Partial<Record<NpcSection, number>>>({});
  const [sheet, setSheet] = useState<StaffEditBody>({});
  const [regard, setRegard] = useState<RegardLine[]>([]);
  const [preferences, setPreferences] = useState<PreferenceLine[]>([]);
  const [settings, setSettings] = useState<NpcSettingsPatch>({});
  /** An NPC this form already minted, kept so a retry never mints a second one. */
  const [mintedId, setMintedId] = useState<number | null>(null);
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

  const shown = (section: FoldedSection) => mode === 'detailed' || expanded.has(section);

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

  /** What is sent: only the sections on screen. */
  const draft = (): NpcFormDraft => {
    const copies: Partial<Record<NpcSection, number>> = {};
    for (const [section, source] of Object.entries(sectionCopies) as [NpcSection, number][]) {
      if (section === 'description' || shown(section as FoldedSection)) copies[section] = source;
    }
    const sent = sheet as Record<string, unknown>;
    const keys = [
      ...(shown('identity') ? IDENTITY_KEYS : []),
      ...(shown('background') ? BACKGROUND_KEYS : []),
    ];
    const sentSettings: NpcSettingsPatch = {};
    if (shown('notes') && settings.notes_for_player !== undefined) {
      sentSettings.notes_for_player = settings.notes_for_player;
    }
    if (shown('lending')) {
      if (settings.listed_on_npc_roster !== undefined) {
        sentSettings.listed_on_npc_roster = settings.listed_on_npc_roster;
      }
      if (settings.lend_policy !== undefined) sentSettings.lend_policy = settings.lend_policy;
      if (settings.borrow_audience !== undefined) {
        sentSettings.borrow_audience = settings.borrow_audience;
      }
    }
    return {
      name,
      description,
      preset: mode === 'detailed' ? preset : '',
      startFrom,
      sectionCopies: copies,
      sheet: Object.fromEntries(
        keys.filter((key) => sent[key] !== undefined).map((key) => [key, sent[key]])
      ) as StaffEditBody,
      regard: shown('regard') ? regard : [],
      preferences: shown('preferences') ? preferences : [],
      settings: sentSettings,
    };
  };

  const afterCreate = (entryId: number) => {
    setCreated({ entryId, name: name.trim() });
    void queryClient.invalidateQueries({ queryKey: ['my-roster-entries'] });
  };
  const onMinted = (entryId: number) => {
    setMintedId(entryId);
    void queryClient.invalidateQueries({ queryKey: ['my-roster-entries'] });
  };
  const runCreate = () => {
    if (actorId === null) {
      return Promise.reject(new Error('Puppet a character to create an NPC.'));
    }
    return createNpc(actorId, draft(), mintedId, onMinted);
  };

  const create = useMutation({ mutationFn: runCreate, onSuccess: afterCreate });

  const saveTemplate = useMutation({
    mutationFn: async (asName: string) => {
      let entryId = created?.entryId ?? null;
      if (entryId === null) {
        entryId = await runCreate();
        afterCreate(entryId);
      }
      try {
        await copyNpcAsNew(entryId, asName, true);
      } catch (failure) {
        throw new NpcStepError('saving the template', failure);
      }
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
    setMintedId(null);
    setCreated(null);
    setTemplateName(null);
    setExpanded(new Set());
    create.reset();
    saveTemplate.reset();
  };

  const busy = create.isPending || saveTemplate.isPending;
  const error = (create.error ?? saveTemplate.error) as Error | null;
  const shownName = created?.name ?? name.trim();
  let submitLabel = mode === 'quick' ? 'Create and add to scene' : 'Create NPC';
  if (create.isPending) submitLabel = 'Creating…';
  const lendPolicy = settings.lend_policy ?? DEFAULT_SETTINGS.lend_policy;
  const ownerName = identity.name ? `${identity.name} (you, the creator)` : 'You, the creator';
  const copyFor = (section: NpcSection, title: string, disabled = false) =>
    disabled ? undefined : (
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
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            if (templateName.trim() !== '' && !busy) saveTemplate.mutate(templateName.trim());
          }}
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
        error={error ? failureText(error, created.name) : null}
        onSaveAsTemplate={() => setTemplateName(`${created.name} template`)}
        onNew={reset}
      />
    );
  }

  const nameField = (
    <Field label="Name" htmlFor="npc-name">
      <Input
        id="npc-name"
        value={name}
        disabled={mintedId !== null}
        onChange={(e) => setName(e.target.value)}
      />
    </Field>
  );
  const startFromPicker = (label: string) => (
    <Field label={label} htmlFor="npc-start-from">
      <select
        id="npc-start-from"
        className={selectClass}
        value={startFrom ?? ''}
        onChange={(e) => setStartFrom(e.target.value === '' ? null : Number(e.target.value))}
      >
        <option value="">{'—'}</option>
        {sources.map((source) => (
          <option key={source.id} value={source.id}>
            {source.label}
          </option>
        ))}
      </select>
    </Field>
  );
  const descriptionInput = (
    <Textarea
      id="npc-description"
      aria-label="Description"
      rows={8}
      className="resize-y"
      value={description}
      onChange={(e) => setDescription(e.target.value)}
    />
  );

  const sections = (
    <>
      {shown('identity') && (
        <FormSection title="Who they are" copy={copyFor('identity', 'Who they are')}>
          <div className="flex flex-wrap items-start gap-4">
            {mode === 'detailed' && (
              <Avatar className="h-20 w-20">
                <AvatarFallback>{initials(name)}</AvatarFallback>
              </Avatar>
            )}
            <div className="grid min-w-[14rem] flex-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {mode === 'detailed' && nameField}
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
            </div>
          </div>
        </FormSection>
      )}

      {mode === 'detailed' && (
        <FormSection title="Description" copy={copyFor('description', 'Description')}>
          {descriptionInput}
        </FormSection>
      )}

      {shown('background') && (
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
      )}

      {/* A stat block is applied at the mint, so it and a Powers copy exclude each other. */}
      {shown('powers') && (
        <FormSection
          title="Powers"
          copy={copyFor('powers', 'Powers', mode === 'detailed' && preset !== '')}
        />
      )}

      {shown('regard') && (
        <FormSection
          title="Who they favor and oppose"
          copy={copyFor('regard', 'Who they favor and oppose')}
        >
          <NpcRegardEditor lines={regard} onChange={setRegard} />
        </FormSection>
      )}

      {shown('preferences') && (
        <FormSection title="What works on them" copy={copyFor('preferences', 'What works on them')}>
          <NpcPreferenceEditor traits={[]} lines={preferences} onChange={setPreferences} />
        </FormSection>
      )}

      {shown('notes') && (
        <FormSection title="Notes for whoever plays them">
          <Textarea
            aria-label="Notes for whoever plays them"
            rows={10}
            className="resize-y"
            value={settings.notes_for_player ?? ''}
            onChange={(e) => setSetting('notes_for_player', e.target.value)}
          />
        </FormSection>
      )}

      {shown('lending') && (
        <FormSection title="Owner and lending">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <span id="npc-owner-label" className="text-xs font-medium text-muted-foreground">
                Owner
              </span>
              <span aria-labelledby="npc-owner-label" className="flex h-9 items-center text-sm">
                {ownerName}
              </span>
            </div>
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
      )}
    </>
  );

  return (
    <form
      className="flex flex-col gap-4"
      aria-label="New NPC"
      onKeyDown={holdEnter}
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
              {nameField}
              {startFromPicker('Copy from')}
            </div>
          </div>
          {descriptionInput}
          {sections}
          {QUICK_CHIPS.some((chip) => !expanded.has(chip.section)) && (
            <div className="flex flex-wrap gap-2">
              {QUICK_CHIPS.filter((chip) => !expanded.has(chip.section)).map((chip) => (
                <Button
                  key={chip.section}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="border-dashed"
                  onClick={() => setExpanded((current) => new Set(current).add(chip.section))}
                >
                  + {chip.label}
                </Button>
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <FormSection title="Start from">
            <div className="grid gap-3 sm:grid-cols-2">
              {startFromPicker('Copy an NPC or template')}
              <Field label="Stat block" htmlFor="npc-preset">
                <select
                  id="npc-preset"
                  className={selectClass}
                  value={preset}
                  disabled={sectionCopies.powers !== undefined}
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
          {sections}
        </>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {failureText(error, shownName)}
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
  error: string | null;
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
          {error}
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
      <NpcPowersPanel entryId={created.entryId} />
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
