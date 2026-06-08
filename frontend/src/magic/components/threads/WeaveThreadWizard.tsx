/**
 * WeaveThreadWizard — multi-step modal for weaving a new Thread.
 *
 * Steps:
 *   1. Pick anchor kind (TargetKind) — disabled if character has no unlock for that kind.
 *   2. Pick anchor — kind-specific picker. FACET, COVENANT_ROLE, TRAIT, TECHNIQUE, ROOM,
 *      and RELATIONSHIP_TRACK are supported; RELATIONSHIP_CAPSTONE is deferred per spec.
 *   3. Pick resonance — combobox over useCharacterResonances().
 *   4. Narrative — optional name (max 120) and description.
 *   5. Confirm — summary card + [Weave] button.
 *
 * On success: close modal, navigate to /threads/{newThread.id}.
 * On error: show server message inline, user can retry.
 *
 * Internal step state — does NOT use react-router subroutes.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { useCharacterResonances, useWeaveThread } from '../../queries';
import type {
  CharacterResonance,
  RelationshipTrack,
  RoomBrief,
  TargetKind,
  ThreadHubSummary,
} from '../../types';
import { apiFetch } from '@/evennia_replacements/api';

// ---------------------------------------------------------------------------
// Local anchor-picker data types
// ---------------------------------------------------------------------------

interface AnchorOption {
  id: number;
  label: string;
  sublabel?: string;
}

// ---------------------------------------------------------------------------
// Kind metadata
// ---------------------------------------------------------------------------

interface KindMeta {
  label: string;
  supported: boolean;
  /** Human-facing reason when unsupported. */
  unsupportedNote?: string;
}

const KIND_META: Record<string, KindMeta> = {
  TRAIT: { label: 'Trait', supported: true },
  TECHNIQUE: { label: 'Technique', supported: true },
  ROOM: { label: 'Room', supported: true },
  FACET: { label: 'Facet', supported: true },
  COVENANT_ROLE: { label: 'Covenant Role', supported: true },
  RELATIONSHIP_TRACK: { label: 'Relationship Track', supported: true },
  RELATIONSHIP_CAPSTONE: {
    label: 'Relationship Capstone',
    supported: false,
    unsupportedNote: 'Not yet available — deferred.',
  },
};

/** Ordered list of all known TargetKind values for display. */
const ALL_KINDS: TargetKind[] = [
  'TRAIT',
  'TECHNIQUE',
  'FACET',
  'ROOM',
  'COVENANT_ROLE',
  'RELATIONSHIP_TRACK',
  'RELATIONSHIP_CAPSTONE',
];

// ---------------------------------------------------------------------------
// Anchor fetchers (called per-kind on demand)
// ---------------------------------------------------------------------------

async function fetchFacetOptions(): Promise<AnchorOption[]> {
  const res = await apiFetch('/api/magic/facets/');
  if (!res.ok) throw new Error('Failed to load facets');
  const data = (await res.json()) as Array<{ id: number; full_path: string; name: string }>;
  return data.map((f) => ({ id: f.id, label: f.full_path || f.name }));
}

async function fetchCovenantRoleOptions(): Promise<AnchorOption[]> {
  const res = await apiFetch('/api/covenants/character-roles/');
  if (!res.ok) throw new Error('Failed to load covenant roles');
  type PagedResult = {
    results?: Array<{
      id: number;
      covenant_role: { id: number; name: string; covenant_type_display: string };
      is_active: boolean;
    }>;
  };
  const data = (await res.json()) as
    | PagedResult
    | Array<{
        id: number;
        covenant_role: { id: number; name: string; covenant_type_display: string };
        is_active: boolean;
      }>;
  const rows = Array.isArray(data) ? data : (data.results ?? []);
  // Deduplicate by covenant_role.id — weaving only cares about the role, not the assignment row.
  const seen = new Set<number>();
  const options: AnchorOption[] = [];
  for (const row of rows) {
    if (seen.has(row.covenant_role.id)) continue;
    seen.add(row.covenant_role.id);
    options.push({
      id: row.covenant_role.id,
      label: row.covenant_role.name,
      sublabel: `${row.covenant_role.covenant_type_display}${row.is_active ? '' : ' (past)'}`,
    });
  }
  return options;
}

function fetchTraitOptions(summary: ThreadHubSummary | undefined): AnchorOption[] {
  return (summary?.weavable_traits ?? []).map((t) => ({
    id: t.trait_id,
    label: t.name,
    sublabel: `${t.trait_type} · ${t.display_value}`,
  }));
}

function fetchTechniqueOptions(summary: ThreadHubSummary | undefined): AnchorOption[] {
  return (summary?.weavable_techniques ?? []).map((t) => ({
    id: t.technique_id,
    label: t.name,
    sublabel: t.gift_name,
  }));
}

async function fetchRoomOptions(summary: ThreadHubSummary | undefined): Promise<AnchorOption[]> {
  const propertyIds = summary?.room_property_ids ?? [];
  if (propertyIds.length === 0) return [];
  const qs = propertyIds.map((id) => `property_id=${id}`).join('&');
  const res = await apiFetch(`/api/magic/rooms-by-property/?${qs}`);
  if (!res.ok) throw new Error('Failed to load rooms');
  const data = (await res.json()) as RoomBrief[];
  return data.map((r) => ({ id: r.id, label: r.name }));
}

async function fetchRelationshipTrackOptions(
  summary: ThreadHubSummary | undefined
): Promise<AnchorOption[]> {
  const allowedIds = new Set(summary?.weavable_relationship_track_ids ?? []);
  if (allowedIds.size === 0) return [];
  const res = await apiFetch('/api/relationships/tracks/');
  if (!res.ok) throw new Error('Failed to load relationship tracks');
  const data = (await res.json()) as RelationshipTrack[];
  return data.filter((t) => allowedIds.has(t.id)).map((t) => ({ id: t.id, label: t.name }));
}

async function fetchAnchorOptions(
  kind: TargetKind,
  summary: ThreadHubSummary | undefined
): Promise<AnchorOption[]> {
  switch (kind) {
    case 'FACET':
      return fetchFacetOptions();
    case 'COVENANT_ROLE':
      return fetchCovenantRoleOptions();
    case 'TRAIT':
      return fetchTraitOptions(summary);
    case 'TECHNIQUE':
      return fetchTechniqueOptions(summary);
    case 'ROOM':
      return fetchRoomOptions(summary);
    case 'RELATIONSHIP_TRACK':
      return fetchRelationshipTrackOptions(summary);
    default:
      return [];
  }
}

// ---------------------------------------------------------------------------
// Wizard state
// ---------------------------------------------------------------------------

type WizardStep = 1 | 2 | 3 | 4 | 5;

interface WizardState {
  step: WizardStep;
  selectedKind: TargetKind | null;
  selectedAnchorId: number | null;
  selectedAnchorLabel: string | null;
  selectedResonanceId: number | null;
  name: string;
  description: string;
}

const INITIAL_STATE: WizardState = {
  step: 1,
  selectedKind: null,
  selectedAnchorId: null,
  selectedAnchorLabel: null,
  selectedResonanceId: null,
  name: '',
  description: '',
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface WeaveThreadWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summary: ThreadHubSummary | undefined;
  /**
   * PK of the acting character sheet — the character that will own the
   * newly woven thread. The wizard scopes resonance lookup to this
   * sheet so users with alts only see the right character's resonances.
   * ``undefined`` when there is no active character; the wizard renders
   * an empty state in that case.
   */
  characterSheetId: number | undefined;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function WeaveThreadWizard({
  open,
  onOpenChange,
  summary,
  characterSheetId,
}: WeaveThreadWizardProps) {
  const navigate = useNavigate();
  const { data: characterResonances, isLoading: resonancesLoading } =
    useCharacterResonances(characterSheetId);
  const { mutate: weaveThread, isPending: weaving, error: weaveError } = useWeaveThread();

  const [state, setState] = useState<WizardState>(INITIAL_STATE);
  const [anchorOptions, setAnchorOptions] = useState<AnchorOption[]>([]);
  const [anchorLoading, setAnchorLoading] = useState(false);
  const [anchorError, setAnchorError] = useState<string | null>(null);

  // Derived eligibility from summary
  const eligibility = summary?.weaving_eligibility ?? {};

  // ---------------------------------------------------------------------------
  // Navigation helpers
  // ---------------------------------------------------------------------------

  function resetAndClose() {
    setState(INITIAL_STATE);
    setAnchorOptions([]);
    setAnchorError(null);
    onOpenChange(false);
  }

  function goBack() {
    setState((prev) => ({ ...prev, step: (prev.step - 1) as WizardStep }));
  }

  async function selectKind(kind: TargetKind) {
    setState((prev) => ({
      ...prev,
      selectedKind: kind,
      selectedAnchorId: null,
      selectedAnchorLabel: null,
      step: 2,
    }));
    setAnchorOptions([]);
    setAnchorError(null);

    const meta = KIND_META[kind];
    if (!meta?.supported) return;

    setAnchorLoading(true);
    try {
      const options = await fetchAnchorOptions(kind, summary);
      setAnchorOptions(options);
    } catch (err) {
      setAnchorError(err instanceof Error ? err.message : 'Failed to load options.');
    } finally {
      setAnchorLoading(false);
    }
  }

  function selectAnchor(option: AnchorOption) {
    setState((prev) => ({
      ...prev,
      selectedAnchorId: option.id,
      selectedAnchorLabel: option.label,
      step: 3,
    }));
  }

  function selectResonance(cr: CharacterResonance) {
    setState((prev) => ({ ...prev, selectedResonanceId: cr.resonance, step: 4 }));
  }

  function goToConfirm() {
    setState((prev) => ({ ...prev, step: 5 }));
  }

  function handleWeave() {
    if (
      !state.selectedKind ||
      state.selectedAnchorId === null ||
      state.selectedResonanceId === null ||
      characterSheetId == null
    ) {
      return;
    }
    weaveThread(
      {
        target_kind: state.selectedKind,
        target_id: state.selectedAnchorId,
        resonance: state.selectedResonanceId,
        character_sheet_id: characterSheetId,
        name: state.name || undefined,
        description: state.description || undefined,
      },
      {
        onSuccess: (newThread) => {
          resetAndClose();
          navigate(`/threads/${newThread.id}`);
        },
      }
    );
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const stepLabel: Record<WizardStep, string> = {
    1: 'Step 1 of 5 — Choose Anchor Kind',
    2: 'Step 2 of 5 — Choose Anchor',
    3: 'Step 3 of 5 — Choose Resonance',
    4: 'Step 4 of 5 — Name Your Thread',
    5: 'Step 5 of 5 — Confirm',
  };

  const selectedResonance = characterResonances?.find(
    (cr) => cr.resonance === state.selectedResonanceId
  );

  // ---------------------------------------------------------------------------
  // Step 1: Kind picker
  // ---------------------------------------------------------------------------

  function renderStep1() {
    return (
      <div className="space-y-3" data-testid="wizard-step-1">
        <p className="text-sm text-muted-foreground">
          Choose what your Thread will be anchored to.
        </p>
        <div className="grid gap-2">
          {ALL_KINDS.map((kind) => {
            const meta = KIND_META[kind] ?? { label: kind, supported: false };
            const hasUnlock = eligibility[kind] === true;
            const noUnlock = !hasUnlock;
            const notSupported = !meta.supported;
            const disabled = noUnlock || notSupported;

            let tooltipText = '';
            if (noUnlock && !notSupported) {
              tooltipText = `Acquire a Thread Weaving Unlock for ${meta.label} first. Browse Teachers to find one.`;
            } else if (notSupported && meta.unsupportedNote) {
              tooltipText = meta.unsupportedNote;
            }

            return (
              <button
                key={kind}
                type="button"
                data-testid={`kind-button-${kind}`}
                disabled={disabled}
                title={tooltipText || undefined}
                onClick={() => selectKind(kind).catch(() => {})}
                className={[
                  'flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors',
                  disabled
                    ? 'cursor-not-allowed opacity-50'
                    : 'hover:bg-accent hover:text-accent-foreground',
                ].join(' ')}
              >
                <span className="flex-1">
                  <span className="font-medium">{meta.label}</span>
                  {disabled && tooltipText && (
                    <span className="ml-2 text-xs text-muted-foreground">({tooltipText})</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Step 2: Anchor picker
  // ---------------------------------------------------------------------------

  function renderStep2() {
    const kind = state.selectedKind;
    const meta = kind ? (KIND_META[kind] ?? { label: kind, supported: false }) : null;

    if (!kind || !meta?.supported) {
      return (
        <div className="space-y-3" data-testid="wizard-step-2-unsupported">
          <p className="text-sm text-muted-foreground">
            {meta?.unsupportedNote ?? 'This anchor kind is not yet supported in the UI.'}
          </p>
          <p className="text-sm">Please choose a different anchor kind.</p>
        </div>
      );
    }

    return (
      <div className="space-y-3" data-testid="wizard-step-2">
        <p className="text-sm text-muted-foreground">
          Select the {meta.label} to anchor your Thread to.
        </p>

        {anchorLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        )}

        {anchorError && (
          <p className="text-sm text-destructive" role="alert" data-testid="anchor-error">
            {anchorError}
          </p>
        )}

        {!anchorLoading && !anchorError && anchorOptions.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="anchor-empty">
            No {meta.label.toLowerCase()} options found. You may not have any qualifying records.
          </p>
        )}

        {!anchorLoading && anchorOptions.length > 0 && (
          <div className="max-h-72 space-y-1 overflow-y-auto" data-testid="anchor-list">
            {anchorOptions.map((opt) => (
              <button
                key={opt.id}
                type="button"
                data-testid={`anchor-option-${opt.id}`}
                onClick={() => selectAnchor(opt)}
                className="flex w-full flex-col items-start rounded-lg border px-4 py-3 text-left hover:bg-accent hover:text-accent-foreground"
              >
                <span className="font-medium">{opt.label}</span>
                {opt.sublabel && (
                  <span className="text-xs text-muted-foreground">{opt.sublabel}</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Step 3: Resonance picker
  // ---------------------------------------------------------------------------

  function renderStep3() {
    return (
      <div className="space-y-3" data-testid="wizard-step-3">
        <p className="text-sm text-muted-foreground">
          Which resonance will power this Thread? Each Thread channels one resonance for currency.
        </p>

        {resonancesLoading && (
          <div className="space-y-2">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        )}

        {!resonancesLoading && (!characterResonances || characterResonances.length === 0) && (
          <p className="text-sm text-muted-foreground" data-testid="resonance-empty">
            No resonances found. Claim a resonance first before weaving.
          </p>
        )}

        {!resonancesLoading && characterResonances && characterResonances.length > 0 && (
          <div className="space-y-2" data-testid="resonance-list">
            {characterResonances.map((cr) => (
              <button
                key={cr.id}
                type="button"
                data-testid={`resonance-option-${cr.resonance}`}
                onClick={() => selectResonance(cr)}
                className="flex w-full items-center gap-3 rounded-lg border px-4 py-3 text-left hover:bg-accent hover:text-accent-foreground"
              >
                <span className="flex-1">
                  <span className="font-medium">{cr.resonance_name}</span>
                  {cr.resonance_detail?.affinity_name && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      {cr.resonance_detail.affinity_name}
                    </span>
                  )}
                </span>
                <span className="text-sm tabular-nums text-muted-foreground">
                  {cr.balance ?? 0} balance
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Step 4: Narrative
  // ---------------------------------------------------------------------------

  function renderStep4() {
    return (
      <div className="space-y-4" data-testid="wizard-step-4">
        <p className="text-sm text-muted-foreground">
          Name your Thread and describe its meaning. Names make Threads easier to find and recall.
        </p>

        <div className="space-y-1.5">
          <Label htmlFor="thread-wizard-name">Name (optional)</Label>
          <Input
            id="thread-wizard-name"
            value={state.name}
            onChange={(e) => setState((prev) => ({ ...prev, name: e.target.value }))}
            maxLength={120}
            placeholder="e.g., The Sorrow I Carry"
            data-testid="wizard-name-input"
          />
          <p className="text-xs text-muted-foreground">
            A memorable name. You can rename it later.
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="thread-wizard-description">Description (optional)</Label>
          <Textarea
            id="thread-wizard-description"
            value={state.description}
            onChange={(e) => setState((prev) => ({ ...prev, description: e.target.value }))}
            placeholder="What does this Thread mean to your character?"
            rows={3}
            data-testid="wizard-description-input"
          />
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Step 5: Confirm
  // ---------------------------------------------------------------------------

  function renderStep5() {
    return (
      <div className="space-y-4" data-testid="wizard-step-5">
        <p className="text-sm text-muted-foreground">Review your Thread before weaving.</p>

        <div className="space-y-2 rounded-lg border p-4 text-sm" data-testid="wizard-summary">
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">Anchor Kind</span>
            <span className="font-medium">
              {state.selectedKind
                ? (KIND_META[state.selectedKind]?.label ?? state.selectedKind)
                : '—'}
            </span>
          </div>
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">Anchor</span>
            <span className="font-medium">{state.selectedAnchorLabel ?? '—'}</span>
          </div>
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">Resonance</span>
            <span className="font-medium">{selectedResonance?.resonance_name ?? '—'}</span>
          </div>
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">Name</span>
            <span className="font-medium">{state.name.trim() || '(unnamed)'}</span>
          </div>
          {state.description.trim() && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">Description</span>
              <span>{state.description.trim()}</span>
            </div>
          )}
        </div>

        {weaveError && (
          <p className="text-sm text-destructive" role="alert" data-testid="wizard-weave-error">
            {weaveError instanceof Error ? weaveError.message : 'Failed to weave thread.'}
          </p>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Footer buttons per step
  // ---------------------------------------------------------------------------

  function renderFooter() {
    switch (state.step) {
      case 1:
        return (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={resetAndClose}>
              Cancel
            </Button>
          </DialogFooter>
        );

      case 2: {
        const kind = state.selectedKind;
        const meta = kind ? KIND_META[kind] : null;
        const isSupported = meta?.supported ?? false;
        return (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={goBack}>
              Back
            </Button>
            {!isSupported && (
              <Button type="button" variant="outline" onClick={goBack}>
                Choose Different Kind
              </Button>
            )}
          </DialogFooter>
        );
      }

      case 3:
        return (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={goBack}>
              Back
            </Button>
          </DialogFooter>
        );

      case 4:
        return (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={goBack}>
              Back
            </Button>
            <Button type="button" onClick={goToConfirm} data-testid="wizard-next-to-confirm">
              Review
            </Button>
          </DialogFooter>
        );

      case 5:
        return (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={goBack} disabled={weaving}>
              Back
            </Button>
            <Button
              type="button"
              onClick={handleWeave}
              disabled={weaving}
              data-testid="wizard-weave-button"
            >
              {weaving ? 'Weaving…' : 'Weave'}
            </Button>
          </DialogFooter>
        );
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Dialog open={open} onOpenChange={resetAndClose}>
      <DialogContent
        className="sm:max-w-lg"
        data-testid="weave-thread-wizard"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle>Weave a New Thread</DialogTitle>
          <p className="text-xs text-muted-foreground" data-testid="wizard-step-label">
            {stepLabel[state.step]}
          </p>
        </DialogHeader>

        <div className="py-2">
          {state.step === 1 && renderStep1()}
          {state.step === 2 && renderStep2()}
          {state.step === 3 && renderStep3()}
          {state.step === 4 && renderStep4()}
          {state.step === 5 && renderStep5()}
        </div>

        {renderFooter()}
      </DialogContent>
    </Dialog>
  );
}
