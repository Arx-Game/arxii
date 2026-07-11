/**
 * StagingPanel — minimal GM battle-staging controls on the battle map page (#2010).
 *
 * Server-authoritative gating: renders only when the viewer's dispatchable
 * registry actions include at least one staging ref (`create_battle`,
 * `stage_battle_map`, `spawn_battle_units`, `enlist_battle_participant`) —
 * no client-side GM-level check. Mirrors `SceneTacticalMap`'s
 * `setTheStageAction` pattern exactly: resolve the active character ->
 * fetch available actions -> find refs by `registry_key` -> dispatch via
 * `useDispatchPlayerAction` (`frontend/src/scenes/components/SceneTacticalMap.tsx:31-72`,
 * mounted from `frontend/src/scenes/pages/SceneDetailPage.tsx:165`).
 *
 * Two render modes:
 *   - No Battle yet for this scene: the empty-battle "Create Battle" form
 *     (name/risk/optional blueprint), dispatching `create_battle`. `create_battle`
 *     always stages a brand-NEW Scene (`CreateBattleAction`,
 *     `src/actions/definitions/battles.py`) — never this page's own `sceneId` — so a
 *     successful create navigates to `/scenes/<data.scene_id>/battle`, the new
 *     battle's own map page, rather than leaving the GM stranded on this now-orphaned
 *     route (#2010 review).
 *   - A Battle exists: Apply Blueprint (with a replace-confirm step when the
 *     battle already has a staged map), Spawn Units, and Enlist Participant
 *     forms — each gated independently on its own action ref being present.
 *
 * The dispatch endpoint always resolves HTTP 200 — business-rule rejections
 * come back as a resolved promise too, not a thrown error (see
 * `actions/views.py` `DispatchActionView`) — so `result.success === false`
 * is the signal that distinguishes an honest failure from a real success
 * (`true`/`null`/`undefined` all read as success; see `DispatchResult` in
 * `combat/types.ts`). A failed dispatch shows the error styling and leaves
 * the form/state alone (nothing changed server-side, so there's nothing to
 * reset and nothing to refetch); a successful dispatch resets its form and
 * invalidates the battle detail + for-scene queries so BattleMapCanvas
 * (#2009) refetches.
 */

import { useMemo, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { fetchAvailableActions } from '@/scenes/actionQueries';
import { fetchScene, sceneKeys } from '@/scenes/queries';
import type { SceneDetail, ScenePersona } from '@/scenes/types';
import type { PlayerAction } from '@/scenes/actionTypes';

import { battleKeys, useBattleMapBlueprintsQuery, useBattleUnitTemplatesQuery } from '../queries';
import { BATTLE_RISK_LEVELS } from '../types';
import type { BattleDetail, BattleRiskLevel } from '../types';

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

const DISPATCH_BUTTON_CLASS =
  'w-full rounded border border-blue-500/40 bg-blue-500/5 px-3 py-1.5 text-xs font-medium text-blue-300 transition-colors hover:bg-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50';

const CREATE_BATTLE_KEY = 'create_battle';
const STAGE_BATTLE_MAP_KEY = 'stage_battle_map';
const SPAWN_BATTLE_UNITS_KEY = 'spawn_battle_units';
const ENLIST_BATTLE_PARTICIPANT_KEY = 'enlist_battle_participant';

function riskLabel(level: BattleRiskLevel): string {
  return level.charAt(0).toUpperCase() + level.slice(1);
}

interface Props {
  sceneId: number;
  /** Slim battle summary (id only needed) — null when the scene has no Battle yet. */
  battle: { id: number } | null;
  /** Full aggregate — null while loading or when there's no battle yet. */
  detail: BattleDetail | null;
}

export function StagingPanel({ sceneId, battle, detail }: Props) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // ---------------------------------------------------------------------------
  // Resolve active character -> characterId for the actions endpoint
  // ---------------------------------------------------------------------------
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  // ---------------------------------------------------------------------------
  // Available actions -> the four staging refs
  // ---------------------------------------------------------------------------
  const { data: actionsData } = useQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId!),
    enabled: characterId !== null,
  });
  const availableActions: PlayerAction[] = actionsData?.results ?? [];

  const findAction = (registryKey: string): PlayerAction | null =>
    availableActions.find(
      (a) => a.ref.backend === 'registry' && a.ref.registry_key === registryKey
    ) ?? null;

  const createBattleAction = findAction(CREATE_BATTLE_KEY);
  const stageBattleMapAction = findAction(STAGE_BATTLE_MAP_KEY);
  const spawnBattleUnitsAction = findAction(SPAWN_BATTLE_UNITS_KEY);
  const enlistParticipantAction = findAction(ENLIST_BATTLE_PARTICIPANT_KEY);

  const hasAnyStagingAction = Boolean(
    createBattleAction || stageBattleMapAction || spawnBattleUnitsAction || enlistParticipantAction
  );

  // ---------------------------------------------------------------------------
  // Dispatch
  // ---------------------------------------------------------------------------
  const { mutateAsync: dispatchAction, isPending } = useDispatchPlayerAction(characterId ?? 0);

  // Actor-only outcome line — the dispatch endpoint always resolves HTTP 200
  // for game-logic rejections; `result.success === false` (see module
  // docstring) is what marks those as failures, while a thrown error
  // (`postDispatchAction`, `frontend/src/combat/api.ts:383-397`) marks a
  // real transport/structural error. Both render with the same error styling.
  const [feedback, setFeedback] = useState<{ text: string; error: boolean } | null>(null);

  /** `result.success === false` is the honest-failure wire signal (#2010 review). */
  function isDispatchFailure(result: { success?: boolean | null }): boolean {
    return result.success === false;
  }

  function invalidateBattleQueries() {
    queryClient.invalidateQueries({ queryKey: battleKeys.forScene(sceneId) });
    if (battle) {
      queryClient.invalidateQueries({ queryKey: battleKeys.detail(battle.id) });
    }
  }

  // ---------------------------------------------------------------------------
  // Scene detail — persona -> character_sheet id lookup for the enlist form
  // ---------------------------------------------------------------------------
  const { data: scene } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId),
    queryFn: () => fetchScene(String(sceneId)),
    enabled: hasAnyStagingAction,
  });
  const eligiblePersonas = (scene?.personas ?? []).filter(
    (p): p is ScenePersona & { character_sheet: number } => p.character_sheet != null
  );

  // ---------------------------------------------------------------------------
  // Catalog pickers — only fetched when the matching action is available
  // ---------------------------------------------------------------------------
  const { data: blueprintsData } = useBattleMapBlueprintsQuery(
    Boolean(createBattleAction || stageBattleMapAction)
  );
  const blueprints = blueprintsData?.results ?? [];

  const { data: templatesData } = useBattleUnitTemplatesQuery(Boolean(spawnBattleUnitsAction));
  const templates = templatesData?.results ?? [];

  // ---------------------------------------------------------------------------
  // Create-battle form (empty-battle state)
  // ---------------------------------------------------------------------------
  const [newBattleName, setNewBattleName] = useState('');
  const [newBattleRisk, setNewBattleRisk] = useState<BattleRiskLevel>('low');
  const [newBattleBlueprintId, setNewBattleBlueprintId] = useState<number | ''>('');

  function handleCreateBattle(event: FormEvent) {
    event.preventDefault();
    if (!createBattleAction || !newBattleName.trim()) return;
    const kwargs: Record<string, unknown> = {
      name: newBattleName.trim(),
      risk_level: newBattleRisk,
    };
    if (newBattleBlueprintId !== '') kwargs.blueprint_id = newBattleBlueprintId;
    dispatchAction({ ref: createBattleAction.ref, kwargs })
      .then((result) => {
        if (isDispatchFailure(result)) {
          setFeedback({ text: result.message ?? 'Could not create battle.', error: true });
          return;
        }
        setFeedback({ text: result.message ?? 'Battle created.', error: false });
        setNewBattleName('');
        setNewBattleBlueprintId('');
        invalidateBattleQueries();
        // create_battle stages a NEW Scene for the battle (CreateBattleAction,
        // src/actions/definitions/battles.py) — it is never the current page's
        // sceneId. Follow the action's own `data.scene_id` to the new battle's
        // map page rather than staying on this now-orphaned route (#2010 review).
        const newSceneId = result.data?.scene_id;
        if (typeof newSceneId === 'number') {
          navigate(`/scenes/${newSceneId}/battle`);
        }
      })
      .catch((err: unknown) =>
        setFeedback({
          text: err instanceof Error ? err.message : 'Could not create battle.',
          error: true,
        })
      );
  }

  // ---------------------------------------------------------------------------
  // Apply-blueprint form (replace requires a confirm step)
  // ---------------------------------------------------------------------------
  const [applyBlueprintId, setApplyBlueprintId] = useState<number | ''>('');
  const [confirmingReplace, setConfirmingReplace] = useState(false);
  const hasStagedMap = (detail?.places.length ?? 0) > 0;

  function handleApplyBlueprint(replace: boolean) {
    if (!stageBattleMapAction || !battle || applyBlueprintId === '') return;
    dispatchAction({
      ref: stageBattleMapAction.ref,
      kwargs: { battle_id: battle.id, blueprint_id: applyBlueprintId, replace },
    })
      .then((result) => {
        if (isDispatchFailure(result)) {
          setFeedback({ text: result.message ?? 'Could not apply blueprint.', error: true });
          return;
        }
        setFeedback({ text: result.message ?? 'Blueprint applied.', error: false });
        setConfirmingReplace(false);
        invalidateBattleQueries();
      })
      .catch((err: unknown) =>
        setFeedback({
          text: err instanceof Error ? err.message : 'Could not apply blueprint.',
          error: true,
        })
      );
  }

  // ---------------------------------------------------------------------------
  // Spawn-units form
  // ---------------------------------------------------------------------------
  const [spawnTemplateId, setSpawnTemplateId] = useState<number | ''>('');
  const [spawnSideId, setSpawnSideId] = useState<number | ''>('');
  const [spawnPlaceId, setSpawnPlaceId] = useState<number | ''>('');
  const [spawnCount, setSpawnCount] = useState(1);

  function handleSpawnUnits(event: FormEvent) {
    event.preventDefault();
    if (!spawnBattleUnitsAction || !battle || spawnTemplateId === '' || spawnSideId === '') {
      return;
    }
    const kwargs: Record<string, unknown> = {
      battle_id: battle.id,
      template_id: spawnTemplateId,
      side_id: spawnSideId,
      count: spawnCount,
    };
    if (spawnPlaceId !== '') kwargs.place_id = spawnPlaceId;
    dispatchAction({ ref: spawnBattleUnitsAction.ref, kwargs })
      .then((result) => {
        if (isDispatchFailure(result)) {
          setFeedback({ text: result.message ?? 'Could not spawn units.', error: true });
          return;
        }
        setFeedback({ text: result.message ?? 'Units spawned.', error: false });
        // Reset the per-spawn picks; leave side/place selections in place — a
        // GM commonly spawns several waves into the same side/place in a row.
        setSpawnTemplateId('');
        setSpawnCount(1);
        invalidateBattleQueries();
      })
      .catch((err: unknown) =>
        setFeedback({
          text: err instanceof Error ? err.message : 'Could not spawn units.',
          error: true,
        })
      );
  }

  // ---------------------------------------------------------------------------
  // Enlist-participant form
  // ---------------------------------------------------------------------------
  const [enlistCharacterSheetId, setEnlistCharacterSheetId] = useState<number | ''>('');
  const [enlistSideId, setEnlistSideId] = useState<number | ''>('');
  const [enlistPlaceId, setEnlistPlaceId] = useState<number | ''>('');

  function handleEnlistParticipant(event: FormEvent) {
    event.preventDefault();
    if (
      !enlistParticipantAction ||
      !battle ||
      enlistCharacterSheetId === '' ||
      enlistSideId === ''
    ) {
      return;
    }
    const kwargs: Record<string, unknown> = {
      battle_id: battle.id,
      character_sheet_id: enlistCharacterSheetId,
      side_id: enlistSideId,
    };
    if (enlistPlaceId !== '') kwargs.place_id = enlistPlaceId;
    dispatchAction({ ref: enlistParticipantAction.ref, kwargs })
      .then((result) => {
        if (isDispatchFailure(result)) {
          setFeedback({ text: result.message ?? 'Could not enlist participant.', error: true });
          return;
        }
        setFeedback({ text: result.message ?? 'Participant enlisted.', error: false });
        // Reset the character pick only — leave side/place in place — a GM
        // commonly enlists several characters into the same side/place in a row.
        setEnlistCharacterSheetId('');
        invalidateBattleQueries();
      })
      .catch((err: unknown) =>
        setFeedback({
          text: err instanceof Error ? err.message : 'Could not enlist participant.',
          error: true,
        })
      );
  }

  // ---------------------------------------------------------------------------
  // Server-authoritative gate — nothing to show without any staging ref
  // ---------------------------------------------------------------------------
  if (!hasAnyStagingAction) return null;

  // Actor-only outcome line, shared by every render branch below.
  const feedbackLine = feedback && (
    <p
      className={feedback.error ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}
      data-testid="staging-feedback"
    >
      {feedback.text}
    </p>
  );

  // ---------------------------------------------------------------------------
  // Empty-battle state — create-battle form only
  // ---------------------------------------------------------------------------
  if (!battle) {
    if (!createBattleAction) return null;
    return (
      <div
        className="space-y-2 rounded border border-dashed border-border p-3"
        data-testid="staging-panel-create"
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Create Battle
        </p>
        <form className="space-y-2" onSubmit={handleCreateBattle}>
          <input
            className={SELECT_CLASS}
            placeholder="Battle name"
            value={newBattleName}
            onChange={(e) => setNewBattleName(e.target.value)}
            aria-label="Battle name"
            data-testid="staging-create-name"
          />
          <select
            className={SELECT_CLASS}
            value={newBattleRisk}
            onChange={(e) => setNewBattleRisk(e.target.value as BattleRiskLevel)}
            aria-label="Risk level"
            data-testid="staging-create-risk"
          >
            {BATTLE_RISK_LEVELS.map((level) => (
              <option key={level} value={level}>
                {riskLabel(level)}
              </option>
            ))}
          </select>
          <select
            className={SELECT_CLASS}
            value={newBattleBlueprintId}
            onChange={(e) =>
              setNewBattleBlueprintId(e.target.value === '' ? '' : Number(e.target.value))
            }
            aria-label="Blueprint (optional)"
            data-testid="staging-create-blueprint"
          >
            <option value="">No blueprint</option>
            {blueprints.map((bp) => (
              <option key={bp.id} value={bp.id}>
                {bp.name}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={isPending || !newBattleName.trim()}
            className={DISPATCH_BUTTON_CLASS}
            data-testid="staging-create-submit"
          >
            Create Battle
          </button>
        </form>
        {feedbackLine}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Live-battle staging controls
  // ---------------------------------------------------------------------------
  const sides = detail?.sides ?? [];
  const places = detail?.places ?? [];

  return (
    <div className="space-y-3" data-testid="staging-panel">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Staging</p>
      {feedbackLine}

      {stageBattleMapAction && (
        <div className="space-y-1 rounded bg-muted/30 p-2" data-testid="staging-apply-blueprint">
          <p className="text-xs font-medium">Apply Blueprint</p>
          <select
            className={SELECT_CLASS}
            value={applyBlueprintId}
            onChange={(e) => {
              setApplyBlueprintId(e.target.value === '' ? '' : Number(e.target.value));
              setConfirmingReplace(false);
            }}
            aria-label="Blueprint to apply"
            data-testid="staging-apply-blueprint-select"
          >
            <option value="">Select a blueprint…</option>
            {blueprints.map((bp) => (
              <option key={bp.id} value={bp.id}>
                {bp.name}
              </option>
            ))}
          </select>
          {confirmingReplace ? (
            <div className="space-y-1">
              <p className="text-xs text-destructive">
                This battle already has a staged map — applying will replace it.
              </p>
              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={isPending}
                  onClick={() => handleApplyBlueprint(true)}
                  className="flex-1 rounded border border-destructive/40 bg-destructive/5 px-2 py-1 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="staging-confirm-replace"
                >
                  Confirm Replace
                </button>
                <button
                  type="button"
                  disabled={isPending}
                  onClick={() => setConfirmingReplace(false)}
                  className="flex-1 rounded border border-input px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              disabled={isPending || applyBlueprintId === ''}
              onClick={() => {
                if (hasStagedMap) {
                  setConfirmingReplace(true);
                } else {
                  handleApplyBlueprint(false);
                }
              }}
              className={DISPATCH_BUTTON_CLASS}
              data-testid="staging-apply-blueprint-submit"
            >
              Apply
            </button>
          )}
        </div>
      )}

      {spawnBattleUnitsAction && (
        <form
          className="space-y-1 rounded bg-muted/30 p-2"
          onSubmit={handleSpawnUnits}
          data-testid="staging-spawn-units"
        >
          <p className="text-xs font-medium">Spawn Units</p>
          <select
            className={SELECT_CLASS}
            value={spawnTemplateId}
            onChange={(e) =>
              setSpawnTemplateId(e.target.value === '' ? '' : Number(e.target.value))
            }
            aria-label="Unit template"
            data-testid="staging-spawn-template"
          >
            <option value="">Select a unit template…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <select
            className={SELECT_CLASS}
            value={spawnSideId}
            onChange={(e) => setSpawnSideId(e.target.value === '' ? '' : Number(e.target.value))}
            aria-label="Spawn side"
            data-testid="staging-spawn-side"
          >
            <option value="">Select a side…</option>
            {sides.map((s) => (
              <option key={s.id} value={s.id}>
                {s.covenant_name ?? s.role ?? `Side ${s.id}`}
              </option>
            ))}
          </select>
          <select
            className={SELECT_CLASS}
            value={spawnPlaceId}
            onChange={(e) => setSpawnPlaceId(e.target.value === '' ? '' : Number(e.target.value))}
            aria-label="Spawn place (optional)"
            data-testid="staging-spawn-place"
          >
            <option value="">No place</option>
            {places.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <input
            type="number"
            min={1}
            // Mirrors the server clamp: MAX_TEMPLATE_SPAWN in src/world/battles/staging.py.
            max={20}
            className={SELECT_CLASS}
            value={spawnCount}
            onChange={(e) => setSpawnCount(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
            aria-label="Unit count"
            data-testid="staging-spawn-count"
          />
          <button
            type="submit"
            disabled={isPending || spawnTemplateId === '' || spawnSideId === ''}
            className={DISPATCH_BUTTON_CLASS}
            data-testid="staging-spawn-submit"
          >
            Spawn
          </button>
        </form>
      )}

      {enlistParticipantAction && (
        <form
          className="space-y-1 rounded bg-muted/30 p-2"
          onSubmit={handleEnlistParticipant}
          data-testid="staging-enlist-participant"
        >
          <p className="text-xs font-medium">Enlist Participant</p>
          <select
            className={SELECT_CLASS}
            value={enlistCharacterSheetId}
            onChange={(e) =>
              setEnlistCharacterSheetId(e.target.value === '' ? '' : Number(e.target.value))
            }
            aria-label="Character to enlist"
            data-testid="staging-enlist-character"
          >
            <option value="">Select a character…</option>
            {eligiblePersonas.map((p) => (
              <option key={p.id} value={p.character_sheet}>
                {p.name}
              </option>
            ))}
          </select>
          <select
            className={SELECT_CLASS}
            value={enlistSideId}
            onChange={(e) => setEnlistSideId(e.target.value === '' ? '' : Number(e.target.value))}
            aria-label="Enlist side"
            data-testid="staging-enlist-side"
          >
            <option value="">Select a side…</option>
            {sides.map((s) => (
              <option key={s.id} value={s.id}>
                {s.covenant_name ?? s.role ?? `Side ${s.id}`}
              </option>
            ))}
          </select>
          <select
            className={SELECT_CLASS}
            value={enlistPlaceId}
            onChange={(e) => setEnlistPlaceId(e.target.value === '' ? '' : Number(e.target.value))}
            aria-label="Enlist place (optional)"
            data-testid="staging-enlist-place"
          >
            <option value="">No place</option>
            {places.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={isPending || enlistCharacterSheetId === '' || enlistSideId === ''}
            className={DISPATCH_BUTTON_CLASS}
            data-testid="staging-enlist-submit"
          >
            Enlist
          </button>
        </form>
      )}
    </div>
  );
}
