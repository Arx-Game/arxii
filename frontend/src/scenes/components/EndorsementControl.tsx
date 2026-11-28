/**
 * EndorsementControl (#1138, #2031, #5327) — resonance-picker + endorser badge strip
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
 * A pose's Endorse menu (#5327) lists every resonance in the game under its affinity, from
 * the resonance catalog, whether or not it is in the poser's aura. A pick on a pose that named no
 * resonance waits for the poser: the endorser sees a dashed chip "<Resonance> · waiting for
 * <Name>" with Change (the same menu again) and Withdraw; the poser, the scene's GM and staff
 * see "<Name> proposed <Resonance>" with Accept and Decline. A pose that named its own
 * resonance keeps the one-click "Endorse their X", which needs no accept. The menu is gone
 * once the pose carries a mark, even an undone one. Entry and style endorsements still list
 * `endorsable_resonances` and are unchanged.
 *
 * Hidden entirely when (entry/style):
 *   - endorsable_resonances is empty (nothing to endorse with)
 *   - the pose belongs to the viewer (self-endorsement guard)
 *   - mode === 'whisper' or visibility === 'very_private'
 *   - endorsee_sheet_id is null (impossible in practice but typed)
 * and (pose) when the pose is whispered or very private, or nothing in the control applies to
 * the viewer. The poser never sees the Endorse menu on her own pose, only the picks waiting
 * for her answer.
 *
 * For kind='entry': shows a display-only "Endorsed ✓" indicator when
 * entry_endorsed_by_me is true (entry endorsements are permanent — no retract).
 *
 * For kind='style': the Interaction payload carries no persisted
 * "endorsed by me" flag (verified against
 * `world.scenes.interaction_serializers.InteractionSerializer` — it only
 * exposes `entry_endorsed_by_me`), so the endorsed-✓ indicator is derived from the
 * create-mutation's own `isSuccess` state instead (immutable — no retract,
 * same as entry). A failed style endorsement's backend error (e.g. "not
 * wearing a bound style") is surfaced verbatim via the mutation's `error`.
 */

import { useMemo } from 'react';
import { useViewerPersonaId } from '@/roster/persona';
import { useResonanceCatalog } from '@/magic/queries';
import type { CatalogResonance } from '@/magic/types';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useAnswerPoseEndorsement,
  useChangePoseEndorsement,
  useCreatePoseEndorsement,
  useDeletePoseEndorsement,
  useCreateSceneEntryEndorsement,
  useCreateStyleEndorsement,
} from '../queries';
import type { Interaction, EndorserBadge, PendingPick } from '../types';

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

const PILL_CLASS =
  'rounded-full border border-muted-foreground/30 px-2 py-0.5 text-xs transition-colors hover:border-amber-500/60 disabled:opacity-50';
const OUTLINE_BUTTON_CLASS =
  'rounded-full border border-border px-2 py-0.5 text-xs transition-colors hover:bg-accent disabled:opacity-50';
const PRIMARY_BUTTON_CLASS =
  'rounded-full border border-foreground bg-foreground px-2 py-0.5 text-xs text-background transition-opacity hover:opacity-90 disabled:opacity-50';
const CHIP_CLASS =
  'inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-xs text-amber-700 dark:text-amber-300';

// ---------------------------------------------------------------------------
// Resonance menus
// ---------------------------------------------------------------------------

interface ResonanceOption {
  id: number;
  name: string;
}

interface ResonanceGroup {
  /** The affinity's name; null for a flat list. */
  label: string | null;
  resonances: ResonanceOption[];
}

/** Every resonance in the catalog under its affinity's name, affinities in the order met. */
function groupByAffinity(catalog: readonly CatalogResonance[]): ResonanceGroup[] {
  const groups = new Map<string, ResonanceOption[]>();
  for (const resonance of catalog) {
    const rows = groups.get(resonance.affinity_name) ?? [];
    rows.push({ id: resonance.id, name: resonance.name });
    groups.set(resonance.affinity_name, rows);
  }
  return [...groups].map(([label, resonances]) => ({ label, resonances }));
}

interface ResonanceMenuProps {
  /** What the trigger button says. */
  label: string;
  groups: ResonanceGroup[];
  disabled?: boolean;
  className: string;
  onPick: (resonanceId: number) => void;
}

function ResonanceMenu({ label, groups, disabled, className, onPick }: ResonanceMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" disabled={disabled} className={className}>
          {label}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {groups.map((group) => (
          <div key={group.label ?? 'all'}>
            {group.label !== null && <DropdownMenuLabel>{group.label}</DropdownMenuLabel>}
            {group.resonances.map((r) => (
              <DropdownMenuItem key={r.id} onClick={() => onPick(r.id)}>
                {r.name}
              </DropdownMenuItem>
            ))}
          </div>
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
    <span title={`${badge.persona_name} endorsed with ${resonanceName}`} className={CHIP_CLASS}>
      {badge.persona_name}
    </span>
  );
}

function isPrivatePose(interaction: Interaction): boolean {
  return interaction.mode === 'whisper' || interaction.visibility === 'very_private';
}

// ---------------------------------------------------------------------------
// Pose endorsements (#5327)
// ---------------------------------------------------------------------------

type MyPoseEndorsement = Interaction['my_pose_endorsement'];

interface WaitingPick {
  endorsement_id: number;
  resonance_name: string;
}

function usePoseMutations(sceneId: string) {
  const createPose = useCreatePoseEndorsement(sceneId);
  const deletePose = useDeletePoseEndorsement(sceneId);
  const changePose = useChangePoseEndorsement(sceneId);
  const answerPose = useAnswerPoseEndorsement(sceneId);
  const error =
    createPose.error ?? changePose.error ?? answerPose.error ?? deletePose.error ?? null;
  const busy =
    createPose.isPending || changePose.isPending || answerPose.isPending || deletePose.isPending;
  return { createPose, deletePose, changePose, answerPose, error, busy };
}

type PoseMutations = ReturnType<typeof usePoseMutations>;

/**
 * My own waiting pick, from `pending_picks` or, failing that, from my endorsement row, which
 * says it waits (`awaiting_acceptance`). Either way it is never an endorsed badge or a Retract.
 */
function findWaitingPick(
  picks: PendingPick[],
  myEndorsement: MyPoseEndorsement,
  resonanceNames: Map<number, string>
): WaitingPick | null {
  const listed = picks.find((pick) => pick.mine);
  if (listed) return listed;
  if (!myEndorsement?.awaiting_acceptance) return null;
  return {
    endorsement_id: myEndorsement.id,
    resonance_name: resonanceNames.get(myEndorsement.resonance_id) ?? '',
  };
}

interface PoseControlState {
  isSelfPose: boolean;
  myEndorsement: MyPoseEndorsement;
  minePick: WaitingPick | null;
  answerable: PendingPick[];
  reached: { id: number; name: string } | null;
  canEndorse: boolean;
  endorsers: EndorserBadge[];
}

/** What the pose control shows for this viewer: her own state, the picks she answers, the badges. */
function poseControlState(
  interaction: Interaction,
  viewerPersonaId: number | null,
  hasResonances: boolean,
  resonanceNames: Map<number, string>
): PoseControlState {
  const isSelfPose = viewerPersonaId != null && interaction.persona.id === viewerPersonaId;
  const picks = interaction.pending_picks ?? [];
  const myEndorsement = isSelfPose ? null : interaction.my_pose_endorsement;
  // A pose that carried a mark is never endorsable, undone or not: the server refuses it once
  // a mark ever paid, and a GM's undo does not give the pose back.
  const hasMark = (interaction.act_marks ?? []).length > 0;
  const reached = interaction.reached_resonance ?? null;
  return {
    isSelfPose,
    myEndorsement,
    minePick: findWaitingPick(picks, myEndorsement, resonanceNames),
    answerable: picks.filter((pick) => pick.can_answer && !pick.mine),
    reached,
    canEndorse: !isSelfPose && !hasMark && (reached != null || hasResonances),
    endorsers: isSelfPose ? [] : interaction.pose_endorsers,
  };
}

function PoseAffordance({
  interaction,
  state,
  groups,
  mutations,
}: {
  interaction: Interaction;
  state: PoseControlState;
  groups: ResonanceGroup[];
  mutations: PoseMutations;
}) {
  const { createPose, deletePose, changePose, busy } = mutations;
  const { isSelfPose, minePick, myEndorsement, canEndorse, reached } = state;
  if (minePick != null && !isSelfPose) {
    return (
      <>
        <span data-testid="pose-pick-waiting" className={`${CHIP_CLASS} border-dashed`}>
          {minePick.resonance_name} · waiting for {interaction.persona.name}
        </span>
        <ResonanceMenu
          label="Change"
          groups={groups}
          disabled={busy}
          className={OUTLINE_BUTTON_CLASS}
          onPick={(resonance) => changePose.mutate({ id: minePick.endorsement_id, resonance })}
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => deletePose.mutate(minePick.endorsement_id)}
          data-testid="pose-pick-withdraw"
          className={OUTLINE_BUTTON_CLASS}
        >
          Withdraw
        </button>
      </>
    );
  }
  if (myEndorsement != null) {
    return (
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
    );
  }
  if (canEndorse && reached != null) {
    // A reached pose is endorsed for its reach, which the server reads; nothing is sent.
    return (
      <button
        type="button"
        disabled={createPose.isPending}
        onClick={() => createPose.mutate({ interaction: interaction.id })}
        data-testid="endorse-reached"
        className={PILL_CLASS}
      >
        Endorse their {reached.name}
      </button>
    );
  }
  if (canEndorse) {
    return (
      <ResonanceMenu
        label={ENDORSE_LABELS.pose}
        groups={groups}
        disabled={createPose.isPending}
        className={PILL_CLASS}
        onPick={(resonance) => createPose.mutate({ interaction: interaction.id, resonance })}
      />
    );
  }
  return null;
}

function PoseEndorsementControl({
  interaction,
  sceneId,
}: {
  interaction: Interaction;
  sceneId: string;
}) {
  const viewerPersonaId = useViewerPersonaId();
  const mutations = usePoseMutations(sceneId);
  const { answerPose, busy, error } = mutations;
  const { data: catalog = [] } = useResonanceCatalog();
  const groups = useMemo(() => groupByAffinity(catalog), [catalog]);
  const resonanceNames = useMemo(
    () =>
      new Map([
        ...catalog.map((r): [number, string] => [r.id, r.name]),
        ...interaction.endorsable_resonances.map((r): [number, string] => [r.id, r.name]),
      ]),
    [catalog, interaction.endorsable_resonances]
  );

  if (isPrivatePose(interaction)) return null;

  const state = poseControlState(interaction, viewerPersonaId, groups.length > 0, resonanceNames);
  const { myEndorsement, minePick, answerable, canEndorse, endorsers } = state;

  if (
    !canEndorse &&
    myEndorsement == null &&
    minePick == null &&
    answerable.length === 0 &&
    endorsers.length === 0
  ) {
    return null;
  }

  return (
    <div
      data-testid="endorsement-control-pose"
      className="mt-1 flex flex-wrap items-center gap-1.5"
    >
      <PoseAffordance
        interaction={interaction}
        state={state}
        groups={groups}
        mutations={mutations}
      />

      {/* Picks waiting for the poser, for the poser, the scene's GM and staff. */}
      {answerable.map((pick) => (
        <span
          key={pick.endorsement_id}
          className="flex flex-wrap items-center gap-1.5"
          data-testid={`pose-pick-proposal-${pick.endorsement_id}`}
        >
          <span className={`${CHIP_CLASS} border-dashed`}>
            {pick.endorser_name} proposed {pick.resonance_name}
          </span>
          <button
            type="button"
            disabled={busy}
            onClick={() => answerPose.mutate({ id: pick.endorsement_id, accept: true })}
            data-testid={`pose-pick-accept-${pick.endorsement_id}`}
            className={PRIMARY_BUTTON_CLASS}
          >
            Accept
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => answerPose.mutate({ id: pick.endorsement_id, accept: false })}
            data-testid={`pose-pick-decline-${pick.endorsement_id}`}
            className={OUTLINE_BUTTON_CLASS}
          >
            Decline
          </button>
        </span>
      ))}

      {/* Endorser badges */}
      {endorsers.map((badge) => (
        <BadgeChip
          key={`${badge.persona_id}-${badge.resonance_id}`}
          badge={badge}
          resonanceName={resonanceNames.get(badge.resonance_id) ?? String(badge.resonance_id)}
        />
      ))}

      {/* Backend error: meaningful text (why it was refused), surfaced verbatim. */}
      {error && (
        <span data-testid="endorsement-error" className="text-xs text-destructive">
          {error.message}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Entry and style endorsements (immediate, unchanged by #5327)
// ---------------------------------------------------------------------------

/**
 * Whether the control renders nothing at all: nothing to endorse with, the
 * viewer's own pose, a private/whispered pose, or a payload missing the endorsee
 * sheet the mutation needs.
 */
function isEntryOrStyleHidden(interaction: Interaction, viewerPersonaId: number | null): boolean {
  const isSelfPose = viewerPersonaId != null && interaction.persona.id === viewerPersonaId;
  if (interaction.endorsable_resonances.length === 0 || isSelfPose || isPrivatePose(interaction)) {
    return true;
  }
  // endorsee_sheet_id is typed number | null; it must be present here. If it's somehow
  // null (impossible in practice but typed), hide rather than coerce.
  return interaction.endorsee_sheet_id == null;
}

function EntryOrStyleEndorsementControl({
  interaction,
  sceneId,
  kind,
}: {
  interaction: Interaction;
  sceneId: string;
  kind: 'entry' | 'style';
}) {
  const viewerPersonaId = useViewerPersonaId();
  const createEntry = useCreateSceneEntryEndorsement(sceneId);
  const createStyle = useCreateStyleEndorsement(sceneId);

  // Map resonance id → name for badge tooltips — memoized, unconditional.
  const resonanceMap = useMemo(
    () => new Map(interaction.endorsable_resonances.map((r) => [r.id, r.name])),
    [interaction.endorsable_resonances]
  );
  const groups = useMemo<ResonanceGroup[]>(
    () => [{ label: null, resonances: interaction.endorsable_resonances }],
    [interaction.endorsable_resonances]
  );

  if (isEntryOrStyleHidden(interaction, viewerPersonaId)) return null;

  const activeMutation = kind === 'style' ? createStyle : createEntry;
  const endorsers: EndorserBadge[] = kind === 'entry' ? interaction.entry_endorsers : [];
  // Entry's endorsed state is a persisted server flag; style has none (see
  // module docstring), so it's derived from the create-mutation's own
  // isSuccess — the mutation hook instance persists across re-renders of this
  // component, so the indicator sticks once the immediate grant succeeds.
  const isEndorsedByMe =
    (kind === 'entry' && interaction.entry_endorsed_by_me) ||
    (kind === 'style' && createStyle.isSuccess);

  function handlePickResonance(resonanceId: number) {
    // endorsee_sheet_id is guaranteed non-null here by the guard above.
    activeMutation.mutate({
      endorsee_sheet: interaction.endorsee_sheet_id!,
      scene: Number(sceneId),
      resonance: resonanceId,
    });
  }

  return (
    <div
      data-testid={`endorsement-control-${kind}`}
      className="mt-1 flex flex-wrap items-center gap-1.5"
    >
      {isEndorsedByMe ? (
        /* Entry/style endorsements are permanent — no retract affordance, just a display indicator. */
        <span
          data-testid={`${kind}-endorsed-indicator`}
          className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300"
        >
          Endorsed ✓
        </span>
      ) : (
        <ResonanceMenu
          label={ENDORSE_LABELS[kind]}
          groups={groups}
          disabled={activeMutation.isPending}
          className={PILL_CLASS}
          onPick={handlePickResonance}
        />
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
      {activeMutation.error && (
        <span data-testid="endorsement-error" className="text-xs text-destructive">
          {activeMutation.error.message}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EndorsementControl
// ---------------------------------------------------------------------------

export function EndorsementControl({ interaction, sceneId, kind }: EndorsementControlProps) {
  if (kind === 'pose')
    return <PoseEndorsementControl interaction={interaction} sceneId={sceneId} />;
  return <EntryOrStyleEndorsementControl interaction={interaction} sceneId={sceneId} kind={kind} />;
}
