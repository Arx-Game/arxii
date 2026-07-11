/**
 * WeaveThreadWizard — multi-step modal for weaving a new Thread.
 *
 * Steps:
 *   1. Pick anchor kind (TargetKind) — disabled if character has no unlock for that kind.
 *   2. Pick anchor — kind-specific picker. FACET, COVENANT_ROLE, TRAIT, TECHNIQUE, SANCTUM,
 *      and RELATIONSHIP_TRACK are supported; RELATIONSHIP_CAPSTONE is deferred per spec.
 *      RELATIONSHIP_TRACK is a "with whom" partner-then-track picker (#2159): partner
 *      choices are my scoped relationships with at least one `track_progress` row among
 *      `weavable_relationship_track_ids`; picking a partner reveals that partner's
 *      qualifying tracks (still step 2 — see `renderRelationshipTrackStep2`). The payload
 *      adds `target_persona_id` (the partner's resolved Persona pk) for this kind only.
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
import type { CharacterResonance, TargetKind, ThreadHubSummary } from '../../types';
import { apiFetch } from '@/evennia_replacements/api';
import { getMyOutboundRelationships, getRelationshipDetail } from '@/relationships/api';

// ---------------------------------------------------------------------------
// Local anchor-picker data types
// ---------------------------------------------------------------------------

interface AnchorOption {
  id: number;
  label: string;
  sublabel?: string;
}

/**
 * RELATIONSHIP_TRACK only (#2159): a "with whom" candidate — one of the
 * caller's outbound relationships that has at least one `track_progress` row
 * among `weavable_relationship_track_ids`. `id`/`label` name the partner's
 * CharacterSheet; `personaId` is the partner's resolved Persona pk (the
 * write payload's `target_persona_id`); `qualifyingTracks` are that
 * partner's tracks eligible to anchor a thread (fed straight into the
 * existing `anchorOptions` picker once a partner is chosen).
 */
interface PartnerOption extends AnchorOption {
  personaId: number;
  qualifyingTracks: AnchorOption[];
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
  FACET: { label: 'Facet', supported: true },
  SANCTUM: { label: 'Sanctum', supported: true },
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
  'SANCTUM',
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
    default:
      // RELATIONSHIP_TRACK is handled separately by
      // fetchRelationshipPartnerOptions — it needs a partner-then-track
      // picker, not a flat option list (#2159).
      return [];
  }
}

// ---------------------------------------------------------------------------
// RELATIONSHIP_TRACK partner picker (#2159)
// ---------------------------------------------------------------------------

/** Resolve a CharacterSheet's primary Persona pk (falls back to its first persona). */
async function resolvePrimaryPersonaId(characterSheetId: number): Promise<number | null> {
  const res = await apiFetch(`/api/personas/?character_sheet=${characterSheetId}&page_size=50`);
  if (!res.ok) return null;
  const data = (await res.json()) as {
    results?: Array<{ id: number; persona_type: string }>;
  };
  const personas = data.results ?? [];
  return personas.find((p) => p.persona_type === 'primary')?.id ?? personas[0]?.id ?? null;
}

/**
 * "With whom" step 1 (#2159): my scoped relationships that have at least one
 * `track_progress` row among `weavable_relationship_track_ids` — the only
 * relationships that could possibly anchor a RELATIONSHIP_TRACK thread.
 * `track_progress` only exists on the detail retrieve (the list serializer
 * omits it), so this fetches one detail per outbound relationship. A partner
 * whose CharacterSheet has no resolvable Persona is dropped — there would be
 * no legal `target_persona_id` to submit for them.
 */
async function fetchRelationshipPartnerOptions(
  characterSheetId: number,
  summary: ThreadHubSummary | undefined
): Promise<PartnerOption[]> {
  const allowedTrackIds = new Set(summary?.weavable_relationship_track_ids ?? []);
  if (allowedTrackIds.size === 0) return [];

  const relationships = await getMyOutboundRelationships(characterSheetId);
  const withQualifyingTracks = await Promise.all(
    relationships.map(async (rel) => {
      const detail = await getRelationshipDetail(rel.id);
      const qualifyingTracks = detail.track_progress
        .filter((tp) => allowedTrackIds.has(tp.track))
        .map((tp) => ({ id: tp.track, label: tp.track_name }));
      return { rel, qualifyingTracks };
    })
  );

  const qualifying = withQualifyingTracks.filter((x) => x.qualifyingTracks.length > 0);
  const personaIds = await Promise.all(
    qualifying.map((x) => resolvePrimaryPersonaId(x.rel.target))
  );

  const options: PartnerOption[] = [];
  qualifying.forEach((x, i) => {
    const personaId = personaIds[i];
    if (personaId == null) return;
    options.push({
      id: x.rel.target,
      label: x.rel.target_name,
      personaId,
      qualifyingTracks: x.qualifyingTracks,
    });
  });
  return options;
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
  /** RELATIONSHIP_TRACK only (#2159): the chosen partner's CharacterSheet pk. */
  selectedPartnerSheetId: number | null;
  /** RELATIONSHIP_TRACK only (#2159): the chosen partner's Persona pk — the payload's `target_persona_id`. */
  selectedPartnerPersonaId: number | null;
  selectedPartnerLabel: string | null;
}

const INITIAL_STATE: WizardState = {
  step: 1,
  selectedKind: null,
  selectedAnchorId: null,
  selectedAnchorLabel: null,
  selectedResonanceId: null,
  name: '',
  description: '',
  selectedPartnerSheetId: null,
  selectedPartnerPersonaId: null,
  selectedPartnerLabel: null,
};

// ---------------------------------------------------------------------------
// Step 1 kind button — extracted so the per-kind onClick handler is not nested
// inside renderStep1 → .map() → arrow (keeps function nesting under 4 levels).
// ---------------------------------------------------------------------------

interface KindButtonProps {
  kind: TargetKind;
  hasUnlock: boolean;
  onSelect: (kind: TargetKind) => void;
}

function KindButton({ kind, hasUnlock, onSelect }: KindButtonProps) {
  const meta = KIND_META[kind] ?? { label: kind, supported: false };
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
      type="button"
      data-testid={`kind-button-${kind}`}
      disabled={disabled}
      title={tooltipText || undefined}
      onClick={() => onSelect(kind)}
      className={[
        'flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors',
        disabled ? 'cursor-not-allowed opacity-50' : 'hover:bg-accent hover:text-accent-foreground',
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
}

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
  // RELATIONSHIP_TRACK only (#2159): partner candidates for the "with whom"
  // step, fetched once per kind selection (see selectKind below).
  const [partnerOptions, setPartnerOptions] = useState<PartnerOption[]>([]);

  // Derived eligibility from summary
  const eligibility = summary?.weaving_eligibility ?? {};

  // ---------------------------------------------------------------------------
  // Navigation helpers
  // ---------------------------------------------------------------------------

  function resetAndClose() {
    setState(INITIAL_STATE);
    setAnchorOptions([]);
    setAnchorError(null);
    setPartnerOptions([]);
    onOpenChange(false);
  }

  function goBack() {
    // RELATIONSHIP_TRACK's track sub-view (a partner is already chosen) goes
    // back to the partner list rather than all the way to kind selection —
    // mirrors "Change partner" below (#2159).
    if (state.selectedKind === 'RELATIONSHIP_TRACK' && state.selectedPartnerSheetId != null) {
      changePartner();
      return;
    }
    setState((prev) => ({ ...prev, step: (prev.step - 1) as WizardStep }));
  }

  async function selectKind(kind: TargetKind) {
    setState((prev) => ({
      ...prev,
      selectedKind: kind,
      selectedAnchorId: null,
      selectedAnchorLabel: null,
      selectedPartnerSheetId: null,
      selectedPartnerPersonaId: null,
      selectedPartnerLabel: null,
      step: 2,
    }));
    setAnchorOptions([]);
    setAnchorError(null);
    setPartnerOptions([]);

    const meta = KIND_META[kind];
    if (!meta?.supported) return;

    setAnchorLoading(true);
    try {
      if (kind === 'RELATIONSHIP_TRACK') {
        const options =
          characterSheetId == null
            ? []
            : await fetchRelationshipPartnerOptions(characterSheetId, summary);
        setPartnerOptions(options);
      } else {
        const options = await fetchAnchorOptions(kind, summary);
        setAnchorOptions(options);
      }
    } catch (err) {
      setAnchorError(err instanceof Error ? err.message : 'Failed to load options.');
    } finally {
      setAnchorLoading(false);
    }
  }

  /** RELATIONSHIP_TRACK "with whom" pick — reveals that partner's qualifying tracks. */
  function selectPartner(partner: PartnerOption) {
    setState((prev) => ({
      ...prev,
      selectedPartnerSheetId: partner.id,
      selectedPartnerPersonaId: partner.personaId,
      selectedPartnerLabel: partner.label,
      selectedAnchorId: null,
      selectedAnchorLabel: null,
    }));
    setAnchorOptions(partner.qualifyingTracks);
    setAnchorError(null);
  }

  /** Return from the track sub-view to the partner list (still step 2). */
  function changePartner() {
    setState((prev) => ({
      ...prev,
      selectedPartnerSheetId: null,
      selectedPartnerPersonaId: null,
      selectedPartnerLabel: null,
      selectedAnchorId: null,
      selectedAnchorLabel: null,
    }));
    setAnchorOptions([]);
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
    const isRelationshipTrack = state.selectedKind === 'RELATIONSHIP_TRACK';
    if (isRelationshipTrack && state.selectedPartnerPersonaId == null) {
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
        ...(isRelationshipTrack ? { target_persona_id: state.selectedPartnerPersonaId! } : {}),
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

  function handleSelectKind(kind: TargetKind) {
    selectKind(kind).catch(() => {});
  }

  function renderStep1() {
    return (
      <div className="space-y-3" data-testid="wizard-step-1">
        <p className="text-sm text-muted-foreground">
          Choose what your Thread will be anchored to.
        </p>
        <div className="grid gap-2">
          {ALL_KINDS.map((kind) => (
            <KindButton
              key={kind}
              kind={kind}
              hasUnlock={eligibility[kind] === true}
              onSelect={handleSelectKind}
            />
          ))}
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

    if (kind === 'RELATIONSHIP_TRACK') {
      return renderRelationshipTrackStep2();
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
  // Step 2 (RELATIONSHIP_TRACK only): "with whom" partner-then-track picker (#2159)
  // ---------------------------------------------------------------------------

  function renderRelationshipTrackStep2() {
    if (state.selectedPartnerSheetId == null) {
      return (
        <div className="space-y-3" data-testid="wizard-step-2-partner">
          <p className="text-sm text-muted-foreground">
            Whose relationship track will this Thread anchor to?
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

          {!anchorLoading && !anchorError && partnerOptions.length === 0 && (
            <p className="text-sm text-muted-foreground" data-testid="partner-empty">
              No relationships with a developed track yet. Develop a relationship first.
            </p>
          )}

          {!anchorLoading && partnerOptions.length > 0 && (
            <div className="max-h-72 space-y-1 overflow-y-auto" data-testid="partner-list">
              {partnerOptions.map((partner) => (
                <button
                  key={partner.id}
                  type="button"
                  data-testid={`partner-option-${partner.id}`}
                  onClick={() => selectPartner(partner)}
                  className="flex w-full flex-col items-start rounded-lg border px-4 py-3 text-left hover:bg-accent hover:text-accent-foreground"
                >
                  <span className="font-medium">{partner.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      );
    }

    return (
      <div className="space-y-3" data-testid="wizard-step-2-track">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            Select the track with {state.selectedPartnerLabel}.
          </p>
          <button
            type="button"
            data-testid="wizard-change-partner"
            onClick={changePartner}
            className="shrink-0 text-xs text-muted-foreground underline underline-offset-2"
          >
            Change partner
          </button>
        </div>

        {anchorOptions.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="anchor-empty">
            No qualifying tracks found for this partner.
          </p>
        ) : (
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
          {state.selectedKind === 'RELATIONSHIP_TRACK' && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">Partner</span>
              <span className="font-medium">{state.selectedPartnerLabel ?? '—'}</span>
            </div>
          )}
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
