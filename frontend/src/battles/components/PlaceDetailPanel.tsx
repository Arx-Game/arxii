/**
 * PlaceDetailPanel — the selected battle-map place's roster: units (strength/
 * morale bars, status), player participants (persona name, status), objective
 * holder, and fortifications with integrity. Links out to the bridged combat
 * encounter (world/battles/serializers.py's `encounter_scene_id`, #1236) when
 * one exists.
 *
 * Also hosts `ChampionDuelSection` (#3389 Phase 3) — the Champion-duel
 * challenge is a per-place affordance (same placement as "View encounter"),
 * not part of `BattleActionPanel`.
 */

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Shield, ShieldAlert } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction, useThreatPools } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { registryRef } from '@/combat/duels/DuelChallengeControls';

import { battleKeys } from '../queries';
import type {
  BattlePersonaSummary,
  BattlePlace,
  BattleParticipant,
  BattleSide,
  BattleUnit,
} from '../types';

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

const DISPATCH_BUTTON_CLASS =
  'w-full rounded border border-blue-500/40 bg-blue-500/5 px-3 py-1.5 text-xs font-medium text-blue-300 transition-colors hover:bg-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50';

export interface PlaceDetailPanelProps {
  place: BattlePlace | null;
  sides: BattleSide[];
  units: BattleUnit[];
  participants: BattleParticipant[];
  /** Needed only for ChampionDuelSection's dispatch/invalidation — #3389 Phase 3. */
  sceneId: number;
  battleId: number;
}

/** Both strength and morale run 0..100 (world/battles/constants.py MAX_MORALE; strength starts at its 100 ceiling). */
const MAX_RESOURCE = 100;

function clampResourcePercent(value: number | undefined): number {
  if (value == null) return 0;
  return Math.max(0, Math.min(MAX_RESOURCE, value));
}

function integrityPercent(integrity: number | undefined, maxIntegrity: number | undefined): number {
  if (!integrity || !maxIntegrity) return 0;
  return Math.max(0, Math.min(100, Math.round((integrity / maxIntegrity) * 100)));
}

export function PlaceDetailPanel({
  place,
  sides,
  units,
  participants,
  sceneId,
  battleId,
}: PlaceDetailPanelProps) {
  if (!place) {
    return (
      <div
        className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted-foreground"
        data-testid="battle-place-detail-empty"
      >
        Select a place on the map to see its units and participants.
      </div>
    );
  }

  const placeUnits = units.filter((unit) => unit.place_id === place.id);
  const placeParticipants = participants.filter((participant) => participant.place_id === place.id);
  const holder =
    place.controlled_by_id != null
      ? (sides.find((side) => side.id === place.controlled_by_id) ?? null)
      : null;

  return (
    <div className="flex flex-col gap-4" data-testid="battle-place-detail">
      <div>
        <h3 className="text-sm font-semibold text-foreground">{place.name}</h3>
        <p className="text-xs text-muted-foreground" data-testid="battle-place-objective-holder">
          {holder ? `Held by ${holder.covenant_name ?? holder.role ?? 'a side'}` : 'Uncontrolled'}
        </p>
        {place.encounter_scene_id != null && (
          <Link
            to={`/scenes/${place.encounter_scene_id}`}
            className="text-xs font-medium text-primary underline-offset-2 hover:underline"
            data-testid="battle-place-view-encounter"
          >
            View encounter
          </Link>
        )}
        <ChampionDuelSection
          sceneId={sceneId}
          battleId={battleId}
          place={place}
          participants={participants}
        />
      </div>

      {place.fortifications.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-xs font-semibold uppercase text-muted-foreground">Fortifications</h4>
          {place.fortifications.map((fort) => (
            <div
              key={fort.id}
              className="flex items-center gap-2 text-xs"
              data-testid="battle-fortification-row"
            >
              {fort.breached ? (
                <ShieldAlert className="h-4 w-4 shrink-0 text-destructive" />
              ) : (
                <Shield className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
              <span className="capitalize">{fort.kind ?? 'fortification'}</span>
              <Progress
                value={integrityPercent(fort.integrity, fort.max_integrity)}
                className="h-2 w-24"
              />
              <span className="text-muted-foreground">
                {fort.integrity}/{fort.max_integrity}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">Units</h4>
        {placeUnits.length === 0 ? (
          <p className="text-xs text-muted-foreground">No units at this front.</p>
        ) : (
          placeUnits.map((unit) => (
            <div
              key={unit.id}
              className="rounded-md border border-border p-2"
              data-testid="battle-unit-row"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium text-foreground">{unit.name}</span>
                {unit.status && (
                  <Badge variant="outline" className="shrink-0">
                    {unit.status}
                  </Badge>
                )}
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="w-14 shrink-0 text-[10px] text-muted-foreground">Strength</span>
                <Progress value={clampResourcePercent(unit.strength)} className="h-1.5 w-full" />
                <span className="shrink-0 text-[10px] text-muted-foreground">
                  {unit.strength ?? 0}/{MAX_RESOURCE}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="w-14 shrink-0 text-[10px] text-muted-foreground">Morale</span>
                <Progress value={clampResourcePercent(unit.morale)} className="h-1.5 w-full" />
                <span className="shrink-0 text-[10px] text-muted-foreground">
                  {unit.morale ?? 0}/{MAX_RESOURCE}
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-semibold uppercase text-muted-foreground">Participants</h4>
        {placeParticipants.length === 0 ? (
          <p className="text-xs text-muted-foreground">No player characters at this front.</p>
        ) : (
          placeParticipants.map((participant) => {
            const persona = participant.persona as BattlePersonaSummary | null;
            return (
              <div
                key={participant.id}
                className="flex items-center justify-between gap-2 text-xs"
                data-testid="battle-participant-row"
              >
                <span className="truncate">{persona?.name ?? 'Unknown'}</span>
                {participant.status && <Badge variant="outline">{participant.status}</Badge>}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChampionDuelSection — Phase 3 (#3389): Champion duel challenge, per-place
// ---------------------------------------------------------------------------

interface ChampionDuelSectionProps {
  sceneId: number;
  battleId: number;
  place: BattlePlace;
  participants: BattleParticipant[];
}

/**
 * Renders when the place has no open encounter and the viewer's own
 * `BattleParticipant` row (matched via `character_sheet_id`, same doubling as
 * `BattleActionPanel`'s docstring) reads `is_champion: true` — a read-only
 * visibility hint mirroring `open_champion_duel`'s own `CharacterCovenantRole`
 * gate (`world/battles/serializers.py`). The server-side `NotAChampionError`
 * check inside `ChallengeChampionDuelAction`/`open_champion_duel` is
 * unchanged and remains the actual authority.
 */
function ChampionDuelSection({ sceneId, battleId, place, participants }: ChampionDuelSectionProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const myParticipant = useMemo(
    () => participants.find((p) => p.character_sheet_id === characterId) ?? null,
    [participants, characterId]
  );

  const { mutateAsync: dispatchAction, isPending } = useDispatchPlayerAction(characterId ?? 0);
  const { data: pools = [] } = useThreatPools();

  const [name, setName] = useState('');
  const [threatPoolId, setThreatPoolId] = useState<number | ''>('');
  const [feedback, setFeedback] = useState<{ text: string; error: boolean } | null>(null);
  // Set on a successful dispatch; the effect below navigates once the
  // invalidated battleKeys.detail refetch populates place.encounter_scene_id
  // — the dispatch result only carries encounter_id, not a scene id
  // (ChallengeChampionDuelAction, src/actions/definitions/battles.py).
  const [awaitingEncounter, setAwaitingEncounter] = useState(false);

  useEffect(() => {
    if (awaitingEncounter && place.encounter_scene_id != null) {
      setAwaitingEncounter(false);
      navigate(`/scenes/${place.encounter_scene_id}`);
    }
  }, [awaitingEncounter, place.encounter_scene_id, navigate]);

  const showSection = Boolean(
    place.encounter_scene_id == null && myParticipant?.is_champion && characterId !== null
  );

  if (!showSection) return null;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    dispatchAction(
      registryRef('challenge_champion_duel', {
        battle_place_id: place.id,
        opponent_kwargs: {
          name: trimmedName,
          max_health: 300,
          threat_pool: threatPoolId === '' ? null : threatPoolId,
        },
      })
    )
      .then((result) => {
        if (isDispatchFailure(result)) {
          setFeedback({ text: result.message ?? 'Could not open the duel.', error: true });
          return;
        }
        setFeedback({ text: result.message ?? 'The duel is joined!', error: false });
        setName('');
        setThreatPoolId('');
        queryClient.invalidateQueries({ queryKey: battleKeys.detail(battleId) });
        queryClient.invalidateQueries({ queryKey: battleKeys.forScene(sceneId) });
        setAwaitingEncounter(true);
      })
      .catch((err: unknown) =>
        setFeedback({
          text: err instanceof Error ? err.message : 'Could not open the duel.',
          error: true,
        })
      );
  }

  return (
    <form
      className="mt-2 space-y-1 rounded bg-muted/30 p-2"
      onSubmit={handleSubmit}
      data-testid="champion-duel-section"
    >
      <p className="text-xs font-medium">Challenge Champion Duel</p>
      {feedback && (
        <p
          className={feedback.error ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}
          data-testid="champion-duel-feedback"
        >
          {feedback.text}
        </p>
      )}
      <input
        className={SELECT_CLASS}
        placeholder="Boss name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        aria-label="Boss name"
        data-testid="champion-duel-name"
      />
      <select
        className={SELECT_CLASS}
        value={threatPoolId}
        onChange={(e) => setThreatPoolId(e.target.value === '' ? '' : Number(e.target.value))}
        aria-label="Threat pool (optional)"
        data-testid="champion-duel-threat-pool"
      >
        <option value="">No threat pool</option>
        {pools.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <button
        type="submit"
        disabled={isPending || !name.trim()}
        className={DISPATCH_BUTTON_CLASS}
        data-testid="champion-duel-submit"
      >
        Challenge to Single Combat
      </button>
    </form>
  );
}
