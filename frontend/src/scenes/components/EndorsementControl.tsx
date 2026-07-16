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

export interface EndorsementControlProps {
  interaction: Interaction;
  sceneId: string;
  kind: 'pose' | 'entry' | 'style';
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

  // ----- Guard conditions — render nothing --------------------------------
  const isSelfPose = viewerPersonaId != null && interaction.persona.id === viewerPersonaId;

  if (
    interaction.endorsable_resonances.length === 0 ||
    isSelfPose ||
    interaction.mode === 'whisper' ||
    interaction.visibility === 'very_private'
  ) {
    return null;
  }

  // endorsee_sheet_id is typed number | null; for kind='entry'|'style' it must
  // be present. If it's somehow null (impossible in practice but typed), hide
  // rather than coerce.
  if ((kind === 'entry' || kind === 'style') && interaction.endorsee_sheet_id == null) {
    return null;
  }

  // ----- Data for this kind -----------------------------------------------
  const isPose = kind === 'pose';
  const isEntry = kind === 'entry';
  const isStyle = kind === 'style';
  const endorsers: EndorserBadge[] = isPose
    ? interaction.pose_endorsers
    : isEntry
      ? interaction.entry_endorsers
      : [];

  // ----- Handlers ---------------------------------------------------------
  function handlePickResonance(resonanceId: number) {
    if (isPose) {
      createPose.mutate({ interaction: interaction.id, resonance: resonanceId });
    } else if (isStyle) {
      // endorsee_sheet_id is guaranteed non-null here by the guard above.
      createStyle.mutate({
        endorsee_sheet: interaction.endorsee_sheet_id!,
        scene: Number(sceneId),
        resonance: resonanceId,
      });
    } else {
      createEntry.mutate({
        endorsee_sheet: interaction.endorsee_sheet_id!,
        scene: Number(sceneId),
        resonance: resonanceId,
      });
    }
  }

  // ----- Render -----------------------------------------------------------
  const isPending = isPose
    ? createPose.isPending
    : isStyle
      ? createStyle.isPending
      : createEntry.isPending;
  const myEndorsement = isPose ? interaction.my_pose_endorsement : null;
  const isEndorsed = myEndorsement != null;
  // Entry's endorsed state is a persisted server flag; style has none (see
  // module docstring), so it's derived from the create-mutation's own
  // isSuccess — the mutation hook instance persists across re-renders of this
  // component, so the indicator sticks once the immediate grant succeeds.
  const isImmutableEndorsedByMe =
    (isEntry && interaction.entry_endorsed_by_me) || (isStyle && createStyle.isSuccess);
  const label = isPose ? 'Endorse' : isStyle ? 'Endorse style' : 'Endorse entry';
  const activeError = isPose ? createPose.error : isStyle ? createStyle.error : createEntry.error;

  return (
    <div
      data-testid={`endorsement-control-${kind}`}
      className="mt-1 flex flex-wrap items-center gap-1.5"
    >
      {/* Resonance picker or retract affordance */}
      {isEndorsed ? (
        <button
          type="button"
          disabled={myEndorsement.settled || deletePose.isPending}
          onClick={() => deletePose.mutate(myEndorsement.id)}
          className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
            myEndorsement.settled
              ? 'cursor-not-allowed border-muted-foreground/20 opacity-50'
              : 'border-amber-500 bg-amber-500/10 font-medium hover:bg-amber-500/20'
          }`}
        >
          Retract
        </button>
      ) : isImmutableEndorsedByMe ? (
        /* Entry/style endorsements are permanent — no retract affordance, just a display indicator. */
        <span
          data-testid={`${kind}-endorsed-indicator`}
          className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300"
        >
          Endorsed ✓
        </span>
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              disabled={isPending}
              className="rounded-full border border-muted-foreground/30 px-2 py-0.5 text-xs transition-colors hover:border-amber-500/60 disabled:opacity-50"
            >
              {label}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {interaction.endorsable_resonances.map((r) => (
              <DropdownMenuItem key={r.id} onClick={() => handlePickResonance(r.id)}>
                {r.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      {/* Endorser badges */}
      {endorsers.map((badge) => (
        <BadgeChip
          key={`${badge.persona_id}-${badge.resonance_id}`}
          badge={badge}
          resonanceName={resonanceMap.get(badge.resonance_id) ?? String(badge.resonance_id)}
        />
      ))}

      {/* Backend error — meaningful text (e.g. "not wearing a bound style"), surfaced verbatim. */}
      {activeError && (
        <span data-testid="endorsement-error" className="text-xs text-destructive">
          {activeError.message}
        </span>
      )}
    </div>
  );
}
