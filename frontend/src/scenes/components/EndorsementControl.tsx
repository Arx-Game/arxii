/**
 * EndorsementControl (#1138, #2031) — resonance-picker + endorser badge strip
 * for pose endorsements (weekly PoseEndorsement), scene-entry endorsements
 * (immediate SceneEntryEndorsement), and style-presentation endorsements
 * (immediate StylePresentationEndorsement). Mounts inside PoseUnit.
 *
 * Props:
 *   interaction — the full Interaction payload including endorsement state.
 *   sceneId     — forwarded to mutation hooks for cache invalidation.
 *   kind        — 'pose' | 'entry' | 'style'; drives which mutation fires and
 *                 which badge list / retract affordance is shown.
 *
 * Hidden entirely when:
 *   - endorsable_resonances is empty (nothing to endorse with)
 *   - the pose belongs to the viewer (self-endorsement guard)
 *   - mode === 'whisper' or visibility === 'very_private'
 *   - kind='entry'|'style' and endorsee_sheet_id is null (impossible in
 *     practice but typed)
 *
 * For kind='entry': shows a display-only "Endorsed ✓" indicator when
 * entry_endorsed_by_me is true (entry endorsements are permanent — no retract).
 *
 * For kind='style': the Interaction payload carries no persisted
 * "endorsed by me" flag (verified against
 * `world.scenes.interaction_serializers.InteractionSerializer` — it only
 * exposes `entry_endorsed_by_me`), so the endorsed-✓ indicator is derived from
 * the create-mutation's own `isSuccess` state instead (immutable — no retract,
 * same as entry). A failed style endorsement's backend error (e.g. "not
 * wearing a bound style") is surfaced verbatim via the mutation's `error`.
 */

import { useMemo } from 'react';
import { useAppSelector } from '@/store/hooks';
import { actingPersonaId } from '@/roster/persona';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useCreatePoseEndorsement,
  useDeletePoseEndorsement,
  useCreateSceneEntryEndorsement,
  useCreateStyleEndorsement,
} from '../queries';
import type { Interaction, EndorserBadge } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export type EndorsementKind = 'pose' | 'entry' | 'style';

export interface EndorsementControlProps {
  interaction: Interaction;
  sceneId: string;
  kind: EndorsementKind;
}

const ENDORSE_LABELS: Record<EndorsementKind, string> = {
  pose: 'Endorse',
  entry: 'Endorse entry',
  style: 'Endorse style',
};

/**
 * Whether the control renders nothing at all: nothing to endorse with, the
 * viewer's own pose, a private/whispered pose, or (for entry/style) a payload
 * missing the endorsee sheet the mutation needs.
 */
function isControlHidden(
  interaction: Interaction,
  kind: EndorsementKind,
  viewerPersonaId: number | null | undefined
): boolean {
  const isSelfPose = viewerPersonaId != null && interaction.persona.id === viewerPersonaId;
  if (
    interaction.endorsable_resonances.length === 0 ||
    isSelfPose ||
    interaction.mode === 'whisper' ||
    interaction.visibility === 'very_private'
  ) {
    return true;
  }
  // endorsee_sheet_id is typed number | null; for kind='entry'|'style' it must
  // be present. If it's somehow null (impossible in practice but typed), hide
  // rather than coerce.
  return kind !== 'pose' && interaction.endorsee_sheet_id == null;
}

interface AffordanceProps {
  kind: EndorsementKind;
  resonances: { id: number; name: string }[];
  myEndorsement: { id: number; resonance_id: number; settled: boolean } | null;
  isImmutableEndorsedByMe: boolean;
  isPending: boolean;
  isRetracting: boolean;
  onRetract: (endorsementId: number) => void;
  onPick: (resonanceId: number) => void;
}

/**
 * The one interactive affordance: retract (pose, unsettled), a permanent
 * "Endorsed ✓" indicator (entry/style), or the resonance picker.
 */
function EndorsementAffordance({
  kind,
  resonances,
  myEndorsement,
  isImmutableEndorsedByMe,
  isPending,
  isRetracting,
  onRetract,
  onPick,
}: AffordanceProps) {
  if (myEndorsement != null) {
    return (
      <button
        type="button"
        disabled={myEndorsement.settled || isRetracting}
        onClick={() => onRetract(myEndorsement.id)}
        className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
          myEndorsement.settled
            ? 'cursor-not-allowed border-muted-foreground/20 opacity-50'
            : 'border-amber-500 bg-amber-500/10 font-medium hover:bg-amber-500/20'
        }`}
      >
        Retract
      </button>
    );
  }

  if (isImmutableEndorsedByMe) {
    /* Entry/style endorsements are permanent — no retract affordance, just a display indicator. */
    return (
      <span
        data-testid={`${kind}-endorsed-indicator`}
        className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300"
      >
        Endorsed ✓
      </span>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          disabled={isPending}
          className="rounded-full border border-muted-foreground/30 px-2 py-0.5 text-xs transition-colors hover:border-amber-500/60 disabled:opacity-50"
        >
          {ENDORSE_LABELS[kind]}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {resonances.map((r) => (
          <DropdownMenuItem key={r.id} onClick={() => onPick(r.id)}>
            {r.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---------------------------------------------------------------------------
// Endorser badge chip
// ---------------------------------------------------------------------------

interface BadgeChipProps {
  badge: EndorserBadge;
  resonanceName: string;
}

function BadgeChip({ badge, resonanceName }: BadgeChipProps) {
  return (
    <span
      title={`${badge.persona_name} endorsed with ${resonanceName}`}
      className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-xs text-amber-700 dark:text-amber-300"
    >
      {badge.persona_name}
    </span>
  );
}

// ---------------------------------------------------------------------------
// EndorsementControl
// ---------------------------------------------------------------------------

export function EndorsementControl({ interaction, sceneId, kind }: EndorsementControlProps) {
  // Resolve the viewer's active persona to detect self-pose.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const viewerPersonaId = useMemo(
    () => actingPersonaId(myRosterEntries.find((e) => e.name === activeCharacterName)),
    [myRosterEntries, activeCharacterName]
  );

  // Mutation hooks — must be called unconditionally before any early return.
  const createPose = useCreatePoseEndorsement(sceneId);
  const deletePose = useDeletePoseEndorsement(sceneId);
  const createEntry = useCreateSceneEntryEndorsement(sceneId);
  const createStyle = useCreateStyleEndorsement(sceneId);

  // Map resonance id → name for badge tooltips — memoized, unconditional.
  const resonanceMap = useMemo(
    () => new Map(interaction.endorsable_resonances.map((r) => [r.id, r.name])),
    [interaction.endorsable_resonances]
  );

  if (isControlHidden(interaction, kind, viewerPersonaId)) {
    return null;
  }

  // ----- Data for this kind -----------------------------------------------
  const activeMutation = { pose: createPose, entry: createEntry, style: createStyle }[kind];
  const endorsers: EndorserBadge[] = {
    pose: interaction.pose_endorsers,
    entry: interaction.entry_endorsers,
    style: [] as EndorserBadge[],
  }[kind];
  const myEndorsement = kind === 'pose' ? interaction.my_pose_endorsement : null;
  // Entry's endorsed state is a persisted server flag; style has none (see
  // module docstring), so it's derived from the create-mutation's own
  // isSuccess — the mutation hook instance persists across re-renders of this
  // component, so the indicator sticks once the immediate grant succeeds.
  const isImmutableEndorsedByMe =
    (kind === 'entry' && interaction.entry_endorsed_by_me) ||
    (kind === 'style' && createStyle.isSuccess);

  // ----- Handlers ---------------------------------------------------------
  function handlePickResonance(resonanceId: number) {
    if (kind === 'pose') {
      createPose.mutate({ interaction: interaction.id, resonance: resonanceId });
      return;
    }
    // endorsee_sheet_id is guaranteed non-null here by the guard above.
    const payload = {
      endorsee_sheet: interaction.endorsee_sheet_id!,
      scene: Number(sceneId),
      resonance: resonanceId,
    };
    (kind === 'style' ? createStyle : createEntry).mutate(payload);
  }

  // ----- Render -----------------------------------------------------------
  return (
    <div
      data-testid={`endorsement-control-${kind}`}
      className="mt-1 flex flex-wrap items-center gap-1.5"
    >
      <EndorsementAffordance
        kind={kind}
        resonances={interaction.endorsable_resonances}
        myEndorsement={myEndorsement}
        isImmutableEndorsedByMe={isImmutableEndorsedByMe}
        isPending={activeMutation.isPending}
        isRetracting={deletePose.isPending}
        onRetract={(endorsementId) => deletePose.mutate(endorsementId)}
        onPick={handlePickResonance}
      />

      {/* Endorser badges */}
      {endorsers.map((badge) => (
        <BadgeChip
          key={`${badge.persona_id}-${badge.resonance_id}`}
          badge={badge}
          resonanceName={resonanceMap.get(badge.resonance_id) ?? String(badge.resonance_id)}
        />
      ))}

      {/* Backend error — meaningful text (e.g. "not wearing a bound style"), surfaced verbatim. */}
      {activeMutation.error && (
        <span data-testid="endorsement-error" className="text-xs text-destructive">
          {activeMutation.error.message}
        </span>
      )}
    </div>
  );
}
