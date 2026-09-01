/**
 * BattleActionPanel — participant round-action declarations + GM round
 * lifecycle controls on the battle map page (#3389). Sibling of
 * `StagingPanel.tsx`, mounted from `BattleMapPage.tsx` in the same
 * right-column stack.
 *
 * Renders nothing (`null`) when none of its sub-sections have anything to
 * show for the current viewer — same server-authoritative-gate convention
 * `StagingPanel` establishes (`if (!hasAnyStagingAction) return null;`).
 *
 * Dispatch goes through `useDispatchPlayerAction` + `isDispatchFailure` +
 * `registryRef` (re-exported from `combat/duels/DuelChallengeControls.tsx`,
 * the precedent this spec's Decision 2 names) — direct generic dispatch, not
 * a discoverability adapter, because none of `declare_battle_action`/
 * `begin_battle_round`/`resolve_battle_round`/`conclude_battle` carry a
 * `Prerequisite` a client would need server-truth to discover; availability
 * is decided from data already on the page (the `BattleDetail` aggregate +
 * `SceneDetail.viewer_can_gm`), exactly like `DuelChallengeControls` decides
 * from `encounter`/`isActiveDuel` rather than an available-actions lookup.
 *
 * `characterId` doubles as the viewer's own `character_sheet_id` —
 * `CharacterSheet` is a `primary_key=True` O2O onto `ObjectDB`
 * (`frontend/src/roster/types.ts`'s `MyRosterEntry.character_id` docstring),
 * so no extra lookup is needed to go from "my active character" to "which
 * `BattleParticipant` row is mine."
 */

import { useMemo, useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { registryRef } from '@/combat/duels/DuelChallengeControls';
import { useCastableTechniques } from '@/scenes/actionQueries';
import { fetchScene, sceneKeys } from '@/scenes/queries';
import type { SceneDetail } from '@/scenes/types';

import { battleKeys } from '../queries';
import {
  BATTLE_ACTION_KINDS,
  BATTLE_ACTION_TARGET_SHAPES,
  type BattleActionKind,
  type BattleActionScope,
  type BattleActionTargetShape,
} from '../constants';
import type { BattleDetail, BattlePersonaSummary, BattleRoundSummary } from '../types';

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

const DISPATCH_BUTTON_CLASS =
  'w-full rounded border border-blue-500/40 bg-blue-500/5 px-3 py-1.5 text-xs font-medium text-blue-300 transition-colors hover:bg-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50';

/** Scope this kind is forced/defaulted to when it isn't user-editable (every kind but MOVE). */
const FORCED_SCOPE_FOR_KIND: Record<Exclude<BattleActionKind, 'move'>, BattleActionScope> = {
  strike: 'unit',
  rout: 'unit',
  support: 'unit',
  rescue: 'unit',
  rally: 'unit',
  repel: 'place',
  hold: 'place',
  set_environment: 'place',
  breach: 'unit',
  fortify: 'unit',
  reposition: 'place',
};

interface Props {
  sceneId: number;
  /** Slim battle summary (id only needed) — null when the scene has no Battle yet. */
  battle: { id: number } | null;
  /** Full aggregate — null while loading or when there's no battle yet. */
  detail: BattleDetail | null;
}

export function BattleActionPanel({ sceneId, battle, detail }: Props) {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const myParticipant = useMemo(
    () => detail?.participants.find((p) => p.character_sheet_id === characterId) ?? null,
    [detail, characterId]
  );

  const round = (detail?.round ?? null) as BattleRoundSummary | null;
  const showDeclaration = Boolean(
    battle &&
      detail &&
      myParticipant &&
      characterId !== null &&
      myParticipant.status === 'active' &&
      round?.status === 'declaring'
  );

  // Phase 2 (#3389 Decision 3) — SceneDetail.viewer_can_gm as the client-side
  // hint for the GM lifecycle controls; the strict server-side gate
  // (_actor_may_gm_battle) lives inside each Action's execute() unchanged.
  // Only fetched once a Battle exists — no lifecycle to control otherwise.
  const { data: scene } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId),
    queryFn: () => fetchScene(String(sceneId)),
    enabled: Boolean(battle),
  });
  const showLifecycle = Boolean(battle && detail && scene?.viewer_can_gm && characterId !== null);

  if (!showDeclaration && !showLifecycle) return null;

  return (
    <div className="space-y-3" data-testid="battle-action-panel">
      {showLifecycle && battle && detail && characterId !== null && (
        <BattleLifecycleSection
          sceneId={sceneId}
          battleId={battle.id}
          characterId={characterId}
          round={round}
          isConcluded={detail.concluded_at != null}
        />
      )}
      {showDeclaration && battle && detail && myParticipant && characterId !== null && (
        <BattleDeclarationSection
          sceneId={sceneId}
          battleId={battle.id}
          characterId={characterId}
          detail={detail}
          myParticipant={myParticipant}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BattleLifecycleSection — Phase 2 (#3389): GM round begin/resolve/conclude
// ---------------------------------------------------------------------------

interface LifecycleProps {
  sceneId: number;
  battleId: number;
  characterId: number;
  round: BattleRoundSummary | null;
  isConcluded: boolean;
}

function BattleLifecycleSection({
  sceneId,
  battleId,
  characterId,
  round,
  isConcluded,
}: LifecycleProps) {
  const queryClient = useQueryClient();
  const { mutateAsync: dispatchAction, isPending } = useDispatchPlayerAction(characterId);
  const [feedback, setFeedback] = useState<{ text: string; error: boolean } | null>(null);
  const [confirmingConclude, setConfirmingConclude] = useState(false);

  function invalidateBattleQueries() {
    queryClient.invalidateQueries({ queryKey: battleKeys.detail(battleId) });
    queryClient.invalidateQueries({ queryKey: battleKeys.forScene(sceneId) });
  }

  function dispatchLifecycle(registryKey: string, defaultMessage: string) {
    dispatchAction(registryRef(registryKey))
      .then((result) => {
        if (isDispatchFailure(result)) {
          setFeedback({ text: result.message ?? defaultMessage, error: true });
          return;
        }
        setFeedback({ text: result.message ?? defaultMessage, error: false });
        setConfirmingConclude(false);
        invalidateBattleQueries();
      })
      .catch((err: unknown) =>
        setFeedback({ text: err instanceof Error ? err.message : defaultMessage, error: true })
      );
  }

  const canBegin = round === null || round.status === 'completed';
  const canResolve = round?.status === 'declaring';

  return (
    <div
      className="space-y-2 rounded border border-border p-3"
      data-testid="battle-lifecycle-section"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Round Lifecycle (GM)
      </p>
      {feedback && (
        <p
          className={feedback.error ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}
          data-testid="battle-lifecycle-feedback"
        >
          {feedback.text}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          disabled={isPending || !canBegin}
          onClick={() => dispatchLifecycle('begin_battle_round', 'Round begun.')}
          className={DISPATCH_BUTTON_CLASS}
          data-testid="battle-lifecycle-begin"
        >
          Begin Round
        </button>
        <button
          type="button"
          disabled={isPending || !canResolve}
          onClick={() => dispatchLifecycle('resolve_battle_round', 'Round resolved.')}
          className={DISPATCH_BUTTON_CLASS}
          data-testid="battle-lifecycle-resolve"
        >
          Resolve Round
        </button>
      </div>

      {confirmingConclude ? (
        <div className="space-y-1">
          <p className="text-xs text-destructive">
            This force-ends the war. This cannot be undone.
          </p>
          <div className="flex gap-1">
            <button
              type="button"
              disabled={isPending}
              onClick={() => dispatchLifecycle('conclude_battle', 'Battle concluded.')}
              className="flex-1 rounded border border-destructive/40 bg-destructive/5 px-2 py-1 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="battle-lifecycle-confirm-conclude"
            >
              Confirm Conclude
            </button>
            <button
              type="button"
              disabled={isPending}
              onClick={() => setConfirmingConclude(false)}
              className="flex-1 rounded border border-input px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          disabled={isPending || isConcluded}
          onClick={() => setConfirmingConclude(true)}
          className="w-full rounded border border-destructive/40 bg-destructive/5 px-3 py-1.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="battle-lifecycle-conclude"
        >
          Conclude Battle
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BattleDeclarationSection — Phase 1 (#3389): the 12-kind round-action form
// ---------------------------------------------------------------------------

interface DeclarationProps {
  sceneId: number;
  battleId: number;
  characterId: number;
  detail: BattleDetail;
  myParticipant: NonNullable<BattleDetail['participants']>[number];
}

/** The target-picker state a declaration reads from, whatever shape it turns out to need. */
interface TargetSelection {
  targetUnitId: number | '';
  targetAllyId: number | '';
  targetPlaceId: number | '';
  targetFortificationId: number | '';
  repositionDx: string;
  repositionDy: string;
  moveIsCommanderOrder: boolean;
}

/**
 * The target kwargs one action shape needs, or null when a required pick is missing.
 *
 * Every shape names the fields it requires; an unfilled one makes the whole
 * declaration incomplete rather than sending a partial target. A move only
 * needs a unit when it is a commander's order — otherwise you are moving
 * yourself.
 */
function targetKwargs(
  shape: BattleActionTargetShape,
  selection: TargetSelection
): Record<string, unknown> | null {
  const required: Array<[string, number | string]> = [];
  switch (shape) {
    case 'enemy_unit':
      required.push(['target_unit', selection.targetUnitId]);
      break;
    case 'ally':
      required.push(['target_ally', selection.targetAllyId]);
      break;
    case 'place':
      required.push(['target_place', selection.targetPlaceId]);
      break;
    case 'fortification':
      required.push(['target_fortification', selection.targetFortificationId]);
      break;
    case 'move':
      required.push(['target_place', selection.targetPlaceId]);
      if (selection.moveIsCommanderOrder) {
        required.push(['target_unit', selection.targetUnitId]);
      }
      break;
    case 'reposition':
      required.push(
        ['target_place', selection.targetPlaceId],
        ['reposition_dx', selection.repositionDx],
        ['reposition_dy', selection.repositionDy]
      );
      break;
  }

  const kwargs: Record<string, unknown> = {};
  for (const [key, value] of required) {
    if (value === '') return null;
    kwargs[key] = value;
  }
  return kwargs;
}

function BattleDeclarationSection({
  sceneId,
  battleId,
  characterId,
  detail,
  myParticipant,
}: DeclarationProps) {
  const queryClient = useQueryClient();
  const { mutateAsync: dispatchAction, isPending } = useDispatchPlayerAction(characterId);

  const [feedback, setFeedback] = useState<{ text: string; error: boolean } | null>(null);
  const [actionKind, setActionKind] = useState<BattleActionKind>('strike');
  const [techniqueId, setTechniqueId] = useState<number | ''>('');
  const [targetUnitId, setTargetUnitId] = useState<number | ''>('');
  const [targetAllyId, setTargetAllyId] = useState<number | ''>('');
  const [targetPlaceId, setTargetPlaceId] = useState<number | ''>('');
  const [targetFortificationId, setTargetFortificationId] = useState<number | ''>('');
  const [repositionDx, setRepositionDx] = useState('');
  const [repositionDy, setRepositionDy] = useState('');
  // MOVE only: whether this is a self-move (scope=unit) or a commander order
  // on an own-side unit (scope=place) — see the module docstring's scope table.
  const [moveIsCommanderOrder, setMoveIsCommanderOrder] = useState(false);

  const myPersona = myParticipant.persona as BattlePersonaSummary | null;
  const myPersonaId = myPersona?.id ?? null;
  const { data: castableTechniques = [] } = useCastableTechniques(myPersonaId);

  const targetShape = BATTLE_ACTION_TARGET_SHAPES[actionKind];
  const scope: BattleActionScope =
    actionKind === 'move'
      ? moveIsCommanderOrder
        ? 'place'
        : 'unit'
      : FORCED_SCOPE_FOR_KIND[actionKind];

  const opposingUnits = detail.units.filter((u) => u.side_id !== myParticipant.side_id);
  const ownUnits = detail.units.filter((u) => u.side_id === myParticipant.side_id);
  const ownAllies = detail.participants.filter(
    (p) => p.side_id === myParticipant.side_id && p.id !== myParticipant.id
  );
  const selectedPlace = detail.places.find((p) => p.id === targetPlaceId) || null;
  const fortificationOptions = selectedPlace?.fortifications ?? [];

  function resetTargets() {
    setTargetUnitId('');
    setTargetAllyId('');
    setTargetPlaceId('');
    setTargetFortificationId('');
    setRepositionDx('');
    setRepositionDy('');
    setMoveIsCommanderOrder(false);
  }

  function handleKindChange(kind: BattleActionKind) {
    setActionKind(kind);
    resetTargets();
  }

  function buildKwargs(): Record<string, unknown> | null {
    if (techniqueId === '') return null;
    const targets = targetKwargs(targetShape, {
      targetUnitId,
      targetAllyId,
      targetPlaceId,
      targetFortificationId,
      repositionDx,
      repositionDy,
      moveIsCommanderOrder,
    });
    if (targets === null) return null;
    return { technique_id: techniqueId, action_kind: actionKind, scope, ...targets };
  }

  const kwargs = buildKwargs();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!kwargs) return;
    dispatchAction(registryRef('declare_battle_action', kwargs))
      .then((result) => {
        if (isDispatchFailure(result)) {
          setFeedback({ text: result.message ?? 'Could not declare that action.', error: true });
          return;
        }
        setFeedback({ text: result.message ?? 'Action declared.', error: false });
        queryClient.invalidateQueries({ queryKey: battleKeys.detail(battleId) });
        queryClient.invalidateQueries({ queryKey: battleKeys.forScene(sceneId) });
      })
      .catch((err: unknown) =>
        setFeedback({
          text: err instanceof Error ? err.message : 'Could not declare that action.',
          error: true,
        })
      );
  }

  return (
    <div
      className="space-y-2 rounded border border-border p-3"
      data-testid="battle-declaration-section"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Declare Round Action
      </p>
      {myParticipant.declared_this_round && (
        <p
          className="text-xs text-muted-foreground"
          data-testid="battle-declaration-already-declared"
        >
          You have already declared this round — submitting again replaces it.
        </p>
      )}
      {feedback && (
        <p
          className={feedback.error ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}
          data-testid="battle-declaration-feedback"
        >
          {feedback.text}
        </p>
      )}

      <form className="space-y-2" onSubmit={handleSubmit}>
        <select
          className={SELECT_CLASS}
          value={actionKind}
          onChange={(e) => handleKindChange(e.target.value as BattleActionKind)}
          aria-label="Action kind"
          data-testid="battle-declaration-kind"
        >
          {BATTLE_ACTION_KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>

        <select
          className={SELECT_CLASS}
          value={techniqueId}
          onChange={(e) => setTechniqueId(e.target.value === '' ? '' : Number(e.target.value))}
          aria-label="Technique"
          data-testid="battle-declaration-technique"
        >
          <option value="">Select a technique…</option>
          {castableTechniques.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>

        {actionKind === 'move' && (
          <select
            className={SELECT_CLASS}
            value={moveIsCommanderOrder ? 'order' : 'self'}
            onChange={(e) => {
              setMoveIsCommanderOrder(e.target.value === 'order');
              setTargetUnitId('');
            }}
            aria-label="Move kind"
            data-testid="battle-declaration-move-kind"
          >
            <option value="self">Move myself</option>
            <option value="order">Order a unit to move</option>
          </select>
        )}

        <select
          className={SELECT_CLASS}
          value={scope}
          disabled={actionKind !== 'move'}
          onChange={() => {}}
          aria-label="Scope"
          data-testid="battle-declaration-scope"
        >
          <option value="unit">Unit</option>
          <option value="place">Place (front-wide)</option>
        </select>

        {targetShape === 'enemy_unit' && (
          <select
            className={SELECT_CLASS}
            value={targetUnitId}
            onChange={(e) => setTargetUnitId(e.target.value === '' ? '' : Number(e.target.value))}
            aria-label="Target unit"
            data-testid="battle-declaration-target-unit"
          >
            <option value="">Select an enemy unit…</option>
            {opposingUnits.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        )}

        {targetShape === 'ally' && (
          <select
            className={SELECT_CLASS}
            value={targetAllyId}
            onChange={(e) => setTargetAllyId(e.target.value === '' ? '' : Number(e.target.value))}
            aria-label="Target ally"
            data-testid="battle-declaration-target-ally"
          >
            <option value="">Select an ally…</option>
            {ownAllies.map((p) => {
              const allyPersona = p.persona as BattlePersonaSummary | null;
              return (
                <option key={p.id} value={p.id}>
                  {allyPersona?.name ?? `Participant ${p.id}`}
                </option>
              );
            })}
          </select>
        )}

        {(targetShape === 'place' || targetShape === 'move' || targetShape === 'reposition') && (
          <select
            className={SELECT_CLASS}
            value={targetPlaceId}
            onChange={(e) => setTargetPlaceId(e.target.value === '' ? '' : Number(e.target.value))}
            aria-label="Target place"
            data-testid="battle-declaration-target-place"
          >
            <option value="">Select a place…</option>
            {detail.places.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}

        {targetShape === 'move' && moveIsCommanderOrder && (
          <select
            className={SELECT_CLASS}
            value={targetUnitId}
            onChange={(e) => setTargetUnitId(e.target.value === '' ? '' : Number(e.target.value))}
            aria-label="Unit to order"
            data-testid="battle-declaration-move-unit"
          >
            <option value="">Select a unit to move…</option>
            {ownUnits.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        )}

        {targetShape === 'reposition' && (
          <div className="flex gap-2">
            <input
              type="number"
              className={SELECT_CLASS}
              placeholder="dx"
              value={repositionDx}
              onChange={(e) => setRepositionDx(e.target.value)}
              aria-label="Reposition dx"
              data-testid="battle-declaration-reposition-dx"
            />
            <input
              type="number"
              className={SELECT_CLASS}
              placeholder="dy"
              value={repositionDy}
              onChange={(e) => setRepositionDy(e.target.value)}
              aria-label="Reposition dy"
              data-testid="battle-declaration-reposition-dy"
            />
          </div>
        )}

        {targetShape === 'fortification' && (
          <>
            <select
              className={SELECT_CLASS}
              value={targetPlaceId}
              onChange={(e) => {
                setTargetPlaceId(e.target.value === '' ? '' : Number(e.target.value));
                setTargetFortificationId('');
              }}
              aria-label="Fortification's place"
              data-testid="battle-declaration-fortification-place"
            >
              <option value="">Select a place…</option>
              {detail.places
                .filter((p) => p.fortifications.length > 0)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </select>
            <select
              className={SELECT_CLASS}
              value={targetFortificationId}
              onChange={(e) =>
                setTargetFortificationId(e.target.value === '' ? '' : Number(e.target.value))
              }
              aria-label="Target fortification"
              data-testid="battle-declaration-target-fortification"
            >
              <option value="">Select a fortification…</option>
              {fortificationOptions.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.kind ?? 'Fortification'} ({f.integrity}/{f.max_integrity})
                </option>
              ))}
            </select>
          </>
        )}

        <button
          type="submit"
          disabled={isPending || !kwargs}
          className={DISPATCH_BUTTON_CLASS}
          data-testid="battle-declaration-submit"
        >
          Declare Action
        </button>
      </form>
    </div>
  );
}
