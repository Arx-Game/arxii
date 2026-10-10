/**
 * Staff edit mode on the character sheet (#3988, piece A).
 *
 * With the toggle on, every prose and identity field is edited in place: a click opens
 * the input that fits it, Save writes through `PATCH .../staff-edit/` and the answer
 * replaces the sheet in the cache. Prose fields carry their version history, each
 * version restorable. The mode reaches the fields through a context rather than props,
 * so a field deep in the sheet needs only to be wrapped. Off (or for anyone but staff)
 * every wrapper renders exactly the display it was given.
 */

import { useContext, useState, type ReactNode } from 'react';
import { History, Pencil } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import type {
  CharacterSheetPayload,
  CharacterSheetStaffEdit,
  StaffChoiceField,
  StaffEditBody,
  StaffProseField,
} from '@/character_sheets/api';
import {
  useProfileTextVersions,
  useRestoreProfileTextVersion,
  useStaffChoiceOptions,
  useStaffEditMutation,
} from '@/character_sheets/queries';
import { useStaffEditMode } from '@/character_sheets/staffEditMode';
import { Band } from './primitives';
import { StaffEditContext, type StaffEditState } from './staffEditContext';

/** The mode for the fields below it: live only for staff, with the toggle on. */
export function StaffEditProvider({
  sheet,
  children,
}: {
  sheet: CharacterSheetPayload | undefined;
  children: ReactNode;
}) {
  const [on] = useStaffEditMode();
  const value = on && sheet?.staff_edit ? { sheetId: sheet.id, stored: sheet.staff_edit } : null;
  return <StaffEditContext.Provider value={value}>{children}</StaffEditContext.Provider>;
}

/** The sheet header's Edit toggle; drawn only when the payload says this viewer may edit. */
export function StaffEditToggle({ sheet }: { sheet: CharacterSheetPayload | undefined }) {
  const [on, setOn] = useStaffEditMode();
  if (!sheet?.staff_edit) return null;
  return (
    <label className="flex items-center gap-2 text-sm">
      <Switch checked={on} onCheckedChange={setOn} aria-label="Edit" />
      Edit
    </label>
  );
}

type FieldKind = 'prose' | 'line' | 'number' | 'choice' | 'boolean' | 'select';

interface StaffEditableProps {
  field: Exclude<keyof StaffEditBody, never>;
  kind: FieldKind;
  /** What the sheet shows for this field when edit mode is off. */
  display: ReactNode;
  /** The field's name, for the input's label. */
  label: string;
  /** Fixed options for a `select` (a TextChoices field). */
  options?: { value: string; label: string }[];
  /** Number bounds, mirroring the server's. */
  min?: number;
  max?: number;
}

const PROSE_FIELDS = new Set<string>([
  'description',
  'background',
  'concept',
  'real_concept',
  'quote',
  'never_do',
  'protect',
  'fear',
  'obituary',
  'glimpse',
]);

function storedValue(stored: CharacterSheetStaffEdit, field: string): unknown {
  if (PROSE_FIELDS.has(field)) return stored.prose[field as StaffProseField];
  return stored[field as keyof Omit<CharacterSheetStaffEdit, 'prose'>];
}

/**
 * One field in edit mode. Off, the display as given. On, the display (or a dash for an
 * empty field, so an unfinished sheet has a slot to fill) with an edit door; open, the
 * input with Save and Cancel (Ctrl+Enter saves, Esc cancels).
 */
export function StaffEditable(props: StaffEditableProps) {
  const state = useContext(StaffEditContext);
  if (!state) return <>{props.display}</>;
  return <StaffEditField {...props} state={state} />;
}

function isEmpty(display: ReactNode): boolean {
  return display === null || display === undefined || display === '' || display === false;
}

function StaffEditField({
  field,
  kind,
  display,
  label,
  options,
  min,
  max,
  state,
}: StaffEditableProps & { state: StaffEditState }) {
  const [editing, setEditing] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const current = storedValue(state.stored, field);
  const [draft, setDraft] = useState<string>('');
  const save = useStaffEditMutation(state.sheetId);

  const open = () => {
    setDraft(current === null || current === undefined ? '' : String(current));
    setEditing(true);
  };
  const submit = () => {
    let value: unknown = draft;
    if (kind === 'number') value = draft.trim() === '' ? null : Number(draft);
    if (kind === 'choice') value = draft === '' ? null : Number(draft);
    if (kind === 'boolean') value = draft === 'true';
    save.mutate({ [field]: value } as StaffEditBody, { onSuccess: () => setEditing(false) });
  };
  const keys = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      setEditing(false);
    } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey || kind !== 'prose')) {
      event.preventDefault();
      submit();
    }
  };

  if (!editing) {
    return (
      <span
        className="staff-editable inline-flex flex-wrap items-baseline gap-1"
        data-field={field}
      >
        <button
          type="button"
          className="text-left underline decoration-dotted underline-offset-2"
          onClick={open}
          aria-label={`Edit ${label}`}
        >
          {isEmpty(display) ? <span className="opacity-60">—</span> : display}
        </button>
        <Pencil className="h-3 w-3 opacity-60" aria-hidden="true" />
        {kind === 'prose' && (
          <button
            type="button"
            className="inline-flex items-center gap-0.5 text-xs opacity-70 hover:opacity-100"
            onClick={() => setHistoryOpen((value) => !value)}
            aria-expanded={historyOpen}
            aria-label={`History of ${label}`}
          >
            <History className="h-3 w-3" aria-hidden="true" />
          </button>
        )}
        {historyOpen && (
          <ProseHistory sheetId={state.sheetId} field={field as StaffProseField} label={label} />
        )}
      </span>
    );
  }

  return (
    <span className="staff-editable flex w-full flex-col gap-2" data-field={field} onKeyDown={keys}>
      {kind === 'prose' && (
        <Textarea
          aria-label={label}
          value={draft}
          rows={5}
          autoFocus
          onChange={(event) => setDraft(event.target.value)}
        />
      )}
      {(kind === 'line' || kind === 'number') && (
        <Input
          aria-label={label}
          type={kind === 'number' ? 'number' : 'text'}
          min={min}
          max={max}
          value={draft}
          autoFocus
          onChange={(event) => setDraft(event.target.value)}
        />
      )}
      {kind === 'select' && (
        <select
          aria-label={label}
          className="h-9 rounded-md border bg-transparent px-2 text-sm"
          value={draft}
          autoFocus
          onChange={(event) => setDraft(event.target.value)}
        >
          {(options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
      {kind === 'boolean' && (
        <label className="flex items-center gap-2 text-sm">
          <Switch
            aria-label={label}
            checked={draft === 'true'}
            onCheckedChange={(checked) => setDraft(checked ? 'true' : 'false')}
          />
          {label}
        </label>
      )}
      {kind === 'choice' && (
        <ChoicePicker
          field={field as StaffChoiceField}
          label={label}
          value={draft}
          onChange={setDraft}
        />
      )}
      <span className="flex gap-2">
        <Button type="button" size="sm" onClick={submit} disabled={save.isPending}>
          Save
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </span>
    </span>
  );
}

function ChoicePicker({
  field,
  label,
  value,
  onChange,
}: {
  field: StaffChoiceField;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { data: items = [], isLoading } = useStaffChoiceOptions(field, true);
  return (
    <span aria-label={label}>
      <Combobox
        items={items}
        value={value}
        onValueChange={onChange}
        placeholder={isLoading ? 'Loading…' : label}
        allowDeselect
      />
    </span>
  );
}

/** One prose field's past versions, newest first, each with Restore. */
function ProseHistory({
  sheetId,
  field,
  label,
}: {
  sheetId: number;
  field: StaffProseField;
  label: string;
}) {
  const { data: versions = [], isLoading } = useProfileTextVersions(sheetId, true);
  const restore = useRestoreProfileTextVersion(sheetId);
  const rows = versions.filter((version) => version.field === field);
  return (
    <span
      className="mt-1 flex w-full flex-col gap-2 rounded border p-2 text-sm"
      aria-label={`${label} history`}
      role="region"
    >
      {isLoading && <span className="opacity-70">Loading…</span>}
      {!isLoading && rows.length === 0 && <span className="opacity-70">No versions yet.</span>}
      {rows.map((version) => (
        <span key={version.id} className="flex flex-col gap-1 border-b pb-2 last:border-0">
          <span className="text-xs opacity-70">
            {new Date(version.created_at).toLocaleString()}
            {version.ic_date_display ? ` · ${version.ic_date_display}` : ''}
            {version.era_display_name ? ` · ${version.era_display_name}` : ''}
            {version.staff_edited ? ' · staff' : ''}
          </span>
          <span className="line-clamp-3 whitespace-pre-wrap">{version.text || '—'}</span>
          <span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => restore.mutate(version.id)}
              disabled={restore.isPending}
            >
              Restore
            </Button>
          </span>
        </span>
      ))}
    </span>
  );
}

const MARITAL_OPTIONS = [
  { value: 'single', label: 'Single' },
  { value: 'married', label: 'Married' },
  { value: 'widowed', label: 'Widowed' },
  { value: 'divorced', label: 'Divorced' },
];

/**
 * In edit mode, the fields the sheet never draws (the real concept, the obituary, the
 * exact measures, the social rank) and the ones it draws only when filled (the actor's
 * sheet answers, heritage, build, pronouns), so an unfinished sheet has a slot for
 * each. The fields the sheet already draws are edited where they stand.
 */
export function StaffEditBand({ sheet }: { sheet: CharacterSheetPayload }) {
  const state = useContext(StaffEditContext);
  if (!state) return null;
  const { stored } = state;
  const { identity, appearance } = sheet;
  const pronouns = `${identity.pronouns.subject}/${identity.pronouns.object}/${identity.pronouns.possessive}`;
  const rows: { label: string; node: ReactNode }[] = [
    {
      label: 'Real concept',
      node: (
        <StaffEditable
          field="real_concept"
          kind="prose"
          label="Real concept"
          display={stored.prose.real_concept}
        />
      ),
    },
    {
      label: 'They would never',
      node: (
        <StaffEditable
          field="never_do"
          kind="prose"
          label="They would never"
          display={stored.prose.never_do}
        />
      ),
    },
    {
      label: 'Protects at all costs',
      node: (
        <StaffEditable
          field="protect"
          kind="prose"
          label="Protects at all costs"
          display={stored.prose.protect}
        />
      ),
    },
    {
      label: 'Deathly afraid of',
      node: (
        <StaffEditable
          field="fear"
          kind="prose"
          label="Deathly afraid of"
          display={stored.prose.fear}
        />
      ),
    },
    {
      label: 'Obituary',
      node: (
        <StaffEditable
          field="obituary"
          kind="prose"
          label="Obituary"
          display={stored.prose.obituary}
        />
      ),
    },
    {
      label: 'Heritage',
      node: (
        <StaffEditable
          field="heritage"
          kind="choice"
          label="Heritage"
          display={identity.heritage?.name}
        />
      ),
    },
    {
      label: 'Build',
      node: (
        <StaffEditable field="build" kind="choice" label="Build" display={appearance.build?.name} />
      ),
    },
    {
      label: 'Pronouns',
      node: <StaffEditable field="pronouns" kind="choice" label="Pronouns" display={pronouns} />,
    },
    {
      label: 'Tarot reversed',
      node: (
        <StaffEditable
          field="tarot_reversed"
          kind="boolean"
          label="Tarot reversed"
          display={stored.tarot_reversed ? 'Reversed' : 'Upright'}
        />
      ),
    },
    {
      label: 'Born (IC year)',
      node: (
        <StaffEditable
          field="ic_birth_year"
          kind="number"
          label="Born (IC year)"
          display={stored.ic_birth_year}
        />
      ),
    },
    {
      label: 'Height (inches)',
      node: (
        <StaffEditable
          field="true_height_inches"
          kind="number"
          label="Height (inches)"
          min={12}
          max={600}
          display={stored.true_height_inches}
        />
      ),
    },
    {
      label: 'Weight (pounds)',
      node: (
        <StaffEditable
          field="weight_pounds"
          kind="number"
          label="Weight (pounds)"
          min={0}
          display={stored.weight_pounds}
        />
      ),
    },
    {
      label: 'Marital status',
      node: (
        <StaffEditable
          field="marital_status"
          kind="select"
          label="Marital status"
          options={MARITAL_OPTIONS}
          display={MARITAL_OPTIONS.find((o) => o.value === stored.marital_status)?.label}
        />
      ),
    },
    {
      label: 'Vocation',
      node: (
        <StaffEditable field="vocation" kind="line" label="Vocation" display={stored.vocation} />
      ),
    },
    {
      label: 'Social rank',
      node: (
        <StaffEditable
          field="social_rank"
          kind="number"
          label="Social rank"
          min={1}
          max={20}
          display={stored.social_rank}
        />
      ),
    },
  ];
  return (
    <Band title="Staff edit">
      <dl className="refsheet-glance" data-testid="staff-edit-band">
        {rows.map((row) => (
          <div key={row.label} style={{ display: 'contents' }}>
            <dt>{row.label}</dt>
            <dd>{row.node}</dd>
          </div>
        ))}
      </dl>
    </Band>
  );
}
