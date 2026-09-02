/**
 * SubjectRefFields — shared "kind + typed reference" picker (#2001 Task 8).
 *
 * Reused by ProtectedSubjectFormDialog (author-side: declare a protected
 * subject) and RequestClearanceDialog (requester-side: identity-path clearance
 * request) — both need the exact same subject_kind + exactly-one-of
 * {subject_sheet, subject_item, subject_society, subject_organization,
 * subject_label} shape the backend validates
 * (StoryProtectedSubjectSerializer / CustodyClearanceRequestSerializer).
 *
 * Picker availability per kind, following the brief's "reuse where a picker
 * exists, plain id/label input otherwise" guidance (mirrors
 * boundaries/components/TreasuredSubjectFormDialog.tsx's documented gap):
 *
 * - FACTION → society-or-organization toggle + name search, reusing
 *   `searchSocieties`/`searchOrganizations` from `@/events/queries` (the
 *   same pickers `EventInvitations` uses) via `EntitySearchField`.
 * - ASSET (subject_asset, #3561) → name search over NPCAsset via
 *   `searchNpcAssets` from `stories/api.ts`, same `EntitySearchField` as
 *   FACTION. Only `Stake`/`StakeRequest` carry `subject_asset` today -
 *   `StoryProtectedSubject`/`CustodyClearance` (this component's other two
 *   consumers) don't, so `ProtectedSubjectFormDialog` and
 *   `RequestClearanceDialog` pass `excludeKinds={['asset']}` to hide the
 *   ASSET option from their kind selectors - their models have no
 *   `subject_asset` column to submit a pick into.
 * - PERSONAL_JEOPARDY / NPC_FATE (subject_sheet) and ITEM (subject_item) —
 *   no name-search endpoint exists for CharacterSheet or ItemInstance by name
 *   (only retrieve-by-id ViewSets), so these are plain numeric id inputs,
 *   same fallback TreasuredSubjectFormDialog documents for its FK-backed kinds.
 * - LOCATION / CAMPAIGN_TRACK / CUSTOM → freeform subject_label text.
 */

import { useState } from 'react';
import { EntitySearchField } from '@/components/EntitySearchField';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { searchOrganizations, searchSocieties } from '@/events/queries';
import { searchNpcAssets } from '../api';
import type { SubjectKindEnum } from '../types';

import { SUBJECT_KIND_LABELS } from '@/shared/subjectKinds';

export { SUBJECT_KIND_LABELS };

export interface SubjectRefValue {
  subject_kind: SubjectKindEnum;
  subject_sheet: number | null;
  subject_item: number | null;
  subject_society: number | null;
  subject_organization: number | null;
  subject_asset: number | null;
  subject_label: string;
}

export function emptySubjectRef(kind: SubjectKindEnum = 'custom'): SubjectRefValue {
  return {
    subject_kind: kind,
    subject_sheet: null,
    subject_item: null,
    subject_society: null,
    subject_organization: null,
    subject_asset: null,
    subject_label: '',
  };
}

interface Props {
  value: SubjectRefValue;
  onChange: (value: SubjectRefValue) => void;
  disabled?: boolean;
  /** Kinds to hide from the selector, e.g. ['asset'] where the consumer's model has no subject_asset column. */
  excludeKinds?: SubjectKindEnum[];
}

type FactionTarget = 'society' | 'organization';

function numOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function SubjectRefFields({ value, onChange, disabled, excludeKinds }: Props) {
  const [factionTarget, setFactionTarget] = useState<FactionTarget>(
    value.subject_organization != null ? 'organization' : 'society'
  );

  function handleKindChange(kind: SubjectKindEnum) {
    onChange(emptySubjectRef(kind));
  }

  const kindOptions = (Object.keys(SUBJECT_KIND_LABELS) as SubjectKindEnum[]).filter(
    (kind) => !excludeKinds?.includes(kind)
  );

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <Label htmlFor="subject-ref-kind">Kind</Label>
        <Select
          value={value.subject_kind}
          onValueChange={(v) => handleKindChange(v as SubjectKindEnum)}
          disabled={disabled}
        >
          <SelectTrigger id="subject-ref-kind">
            <SelectValue placeholder="Kind" />
          </SelectTrigger>
          <SelectContent>
            {kindOptions.map((kind) => (
              <SelectItem key={kind} value={kind}>
                {SUBJECT_KIND_LABELS[kind]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {(value.subject_kind === 'personal_jeopardy' || value.subject_kind === 'npc_fate') && (
        <div className="space-y-1">
          <Label htmlFor="subject-ref-sheet">Character sheet id</Label>
          <Input
            id="subject-ref-sheet"
            inputMode="numeric"
            value={value.subject_sheet ?? ''}
            onChange={(e) => onChange({ ...value, subject_sheet: numOrNull(e.target.value) })}
            placeholder="e.g. 42"
            disabled={disabled}
          />
          <p className="text-xs text-muted-foreground">
            No name-search picker exists yet for CharacterSheet; enter the numeric id directly.
          </p>
        </div>
      )}

      {value.subject_kind === 'item' && (
        <div className="space-y-1">
          <Label htmlFor="subject-ref-item">Item instance id</Label>
          <Input
            id="subject-ref-item"
            inputMode="numeric"
            value={value.subject_item ?? ''}
            onChange={(e) => onChange({ ...value, subject_item: numOrNull(e.target.value) })}
            placeholder="e.g. 17"
            disabled={disabled}
          />
          <p className="text-xs text-muted-foreground">
            No name-search picker exists yet for ItemInstance; enter the numeric id directly.
          </p>
        </div>
      )}

      {value.subject_kind === 'faction' && (
        <div className="space-y-2">
          <div className="space-y-1">
            <Label htmlFor="subject-ref-faction-target">Faction level</Label>
            <Select
              value={factionTarget}
              onValueChange={(v) => {
                const target = v as FactionTarget;
                setFactionTarget(target);
                onChange({ ...value, subject_society: null, subject_organization: null });
              }}
              disabled={disabled}
            >
              <SelectTrigger id="subject-ref-faction-target">
                <SelectValue placeholder="Society or organization" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="society">Society</SelectItem>
                <SelectItem value="organization">Organization</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {factionTarget === 'society' ? (
            <EntitySearchField
              label="Society"
              placeholder="Search societies…"
              value={value.subject_society}
              onChange={(id) => onChange({ ...value, subject_society: id })}
              search={searchSocieties}
              disabled={disabled}
            />
          ) : (
            <EntitySearchField
              label="Organization"
              placeholder="Search organizations…"
              value={value.subject_organization}
              onChange={(id) => onChange({ ...value, subject_organization: id })}
              search={searchOrganizations}
              disabled={disabled}
            />
          )}
        </div>
      )}

      {value.subject_kind === 'asset' && (
        <EntitySearchField
          label="Asset"
          placeholder="Search NPC assets…"
          value={value.subject_asset}
          onChange={(id) => onChange({ ...value, subject_asset: id })}
          search={searchNpcAssets}
          disabled={disabled}
        />
      )}

      {(value.subject_kind === 'location' ||
        value.subject_kind === 'campaign_track' ||
        value.subject_kind === 'custom') && (
        <div className="space-y-1">
          <Label htmlFor="subject-ref-label">Label</Label>
          <Input
            id="subject-ref-label"
            value={value.subject_label}
            onChange={(e) => onChange({ ...value, subject_label: e.target.value })}
            placeholder="e.g. The old windmill, the Iron Concord treaty"
            disabled={disabled}
          />
        </div>
      )}
    </div>
  );
}
