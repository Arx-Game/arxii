/**
 * GMEncounterControls — the GM's home for encounter-lifecycle actions (#3067):
 * starting a combat encounter, spawning NPC opponents, adding/removing PCs,
 * and manual round control. Two render modes, based on whether an active
 * encounter exists for the scene:
 *
 * - No encounter: a "Start Encounter" affordance, shown only when
 *   `viewerCanGm` — mirrors `Scene.get_viewer_can_gm`
 *   (staff-or-GM-or-owner), which is also what the backend's create gate now
 *   checks (`IsEncounterGMOrStaff.has_permission`, #3067).
 * - Active encounter: full lifecycle controls, shown only when
 *   `encounter.is_gm` — the backend's `IsEncounterGMOrStaff.has_object_permission`
 *   gate every other action here already uses (narrower than viewer_can_gm —
 *   no owner bypass — matching the existing, tested round-control actions).
 *
 * End Encounter (#876) stays on RoundFlow — not duplicated here; this panel
 * is the home for the lifecycle affordances #3067 newly wires (create,
 * add_opponent, add/remove_participant, begin_round, resolve_round, pause).
 *
 * The settings row also carries an Escalation select (#3552), GM-only, backed
 * by the authored escalation-curve catalog; choosing "None" clears the
 * encounter's curve.
 *
 * Lethal duel proposal (#3068): "Start Lethal Duel" is a THIRD, independent
 * affordance shown whenever the viewer has GM standing — regardless of
 * whether a wider party encounter exists — because a climactic one-on-one
 * duel is its own standalone CombatEncounter (`create_lethal_duel`), never a
 * spawn into the current one. Several players can each have their own
 * simultaneous confrontation in the same scene (the ruling's requirement),
 * so this dialog can be opened repeatedly. Submitting it does NOT create an
 * encounter — it creates a PENDING lethal DuelChallenge; the targeted PC's
 * own accept (via the existing duel-challenge inbox / toast,
 * `DuelChallengeNotifier`) is what actually opens the fight. A GM can never
 * force this open.
 */

import { useEffect, useMemo, useState } from 'react';
import type React from 'react';
import { toast } from 'sonner';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import type { LethalDuelTier, OpponentTier, PaceMode, RiskLevel, StakesLevel } from '../api';
import {
  useAddOpponent,
  useAddParticipant,
  useBeginRound,
  useCreateEncounter,
  useCreatureTemplates,
  useEscalationCurves,
  useOpponentDefaults,
  usePauseEncounter,
  useProposeLethalDuel,
  useRemoveOpponent,
  useRemoveParticipant,
  useResolveRound,
  useSpawnCreature,
  useThreatPools,
  useUpdateEncounterSettings,
} from '../queries';
import { isDispatchFailure } from '../types';
import type { EncounterDetail, PositionNode } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface GMEncounterControlsProps {
  sceneId: number;
  /** The scene's active (non-completed) encounter, or null when none exists. */
  encounter: EncounterDetail | null;
  /**
   * Scene-level "can GM" signal for the no-encounter empty state (mirrors
   * `scene.viewer_can_gm`). Ignored once `encounter` exists —
   * `encounter.is_gm` governs then (see file docstring for why the two
   * signals differ).
   */
  viewerCanGm: boolean;
}

const TIER_OPTIONS: { value: OpponentTier; label: string }[] = [
  { value: 'mook', label: 'Mook' },
  { value: 'elite', label: 'Elite' },
  { value: 'boss', label: 'Boss' },
  { value: 'hero_killer', label: 'Hero Killer' },
  { value: 'swarm', label: 'Swarm' },
];

const PACE_OPTIONS: { value: PaceMode; label: string }[] = [
  { value: 'timed', label: 'Timed — auto-resolves on a timer' },
  { value: 'ready', label: 'Ready — resolves once everyone is ready' },
  { value: 'manual', label: 'Manual — GM controls each round' },
];

/** Sentinel Select value for "clear the escalation curve" (#3552): a curve id is
 * never a valid Select value on its own since Radix Select values are strings. */
const NONE_CURVE = 'none';

const STAKES_OPTIONS: { value: StakesLevel; label: string }[] = [
  { value: 'local', label: 'Local' },
  { value: 'regional', label: 'Regional' },
  { value: 'national', label: 'National' },
  { value: 'continental', label: 'Continental' },
  { value: 'world', label: 'World' },
];

const RISK_OPTIONS: { value: RiskLevel; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'high', label: 'High' },
  { value: 'extreme', label: 'Extreme' },
  { value: 'lethal', label: 'Lethal' },
];

// Significant-NPC tiers only — mirrors world.combat.constants.SIGNIFICANT_NPC_TIERS,
// the set create_lethal_duel_challenge validates against.
const LETHAL_TIER_OPTIONS: { value: LethalDuelTier; label: string }[] = [
  { value: 'elite', label: 'Elite' },
  { value: 'boss', label: 'Boss' },
  { value: 'hero_killer', label: 'Hero Killer' },
];

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export function GMEncounterControls({ sceneId, encounter, viewerCanGm }: GMEncounterControlsProps) {
  // Mirrors the file docstring: no-encounter uses the scene-level signal,
  // an active encounter uses the narrower per-encounter GM check — same
  // split the two existing branches already use.
  const canProposeLethalDuel = encounter ? encounter.is_gm : viewerCanGm;

  return (
    <>
      {!encounter && viewerCanGm && <StartEncounterCard sceneId={sceneId} />}
      {encounter && encounter.is_gm && <ActiveGMControls encounter={encounter} />}
      {canProposeLethalDuel && <StartLethalDuelDialog sceneId={sceneId} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Start encounter (no active encounter yet)
// ---------------------------------------------------------------------------

function StartEncounterCard({ sceneId }: { sceneId: number }) {
  const [paceMode, setPaceMode] = useState<PaceMode>('timed');
  const { mutate, isPending } = useCreateEncounter(sceneId);

  function handleStart() {
    mutate(
      { paceMode },
      { onError: (err: Error) => toast.error(err.message || 'Failed to start encounter.') }
    );
  }

  return (
    <div
      className="space-y-2 rounded-md border border-border bg-card p-3"
      data-testid="start-encounter-card"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Combat</p>
      <Select
        value={paceMode}
        onValueChange={(v) => setPaceMode(v as PaceMode)}
        disabled={isPending}
      >
        <SelectTrigger data-testid="start-encounter-pace-select" className="h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PACE_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value} className="text-xs">
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        className="w-full"
        size="sm"
        disabled={isPending}
        onClick={handleStart}
        data-testid="start-encounter-btn"
      >
        {isPending ? 'Starting…' : 'Start Encounter'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Active encounter — full GM controls
// ---------------------------------------------------------------------------

function ActiveGMControls({ encounter }: { encounter: EncounterDetail }) {
  const beginRound = useBeginRound(encounter.id);
  const resolveRound = useResolveRound(encounter.id);
  const pause = usePauseEncounter(encounter.id);
  const removeParticipant = useRemoveParticipant(encounter.id);
  const removeOpponent = useRemoveOpponent(encounter.id);

  // Manual round control is only meaningful in MANUAL pace — TIMED resolves on
  // its own timer, READY resolves once every participant readies up.
  const isManual = encounter.pace_mode === 'manual';
  const canBegin = isManual && encounter.status === 'between_rounds';
  const canResolve = isManual && encounter.status === 'declaring';

  // Unlike encounter.participants (prefetch-scoped to ACTIVE server-side),
  // encounter.opponents carries every status (defeated/fled/removed included) —
  // filter client-side so a removed/defeated opponent doesn't linger with a
  // dangling "Remove" control (#3382).
  const activeOpponents = encounter.opponents.filter((o) => o.status === 'active');

  function handleRemove(participantId: number) {
    removeParticipant.mutate(participantId, {
      onError: (err: Error) => toast.error(err.message || 'Failed to remove participant.'),
    });
  }

  function handleRemoveOpponent(opponentId: number) {
    removeOpponent.mutate(opponentId, {
      onError: (err: Error) => toast.error(err.message || 'Failed to remove opponent.'),
    });
  }

  function handleBeginRound() {
    beginRound.mutate(undefined, {
      onError: (err: Error) => toast.error(err.message || 'Failed to begin round.'),
    });
  }

  function handleResolveRound() {
    resolveRound.mutate(undefined, {
      onError: (err: Error) => toast.error(err.message || 'Failed to resolve round.'),
    });
  }

  function handlePause() {
    pause.mutate(undefined, {
      onError: (err: Error) => toast.error(err.message || 'Failed to toggle pause.'),
    });
  }

  const renderPause = () => {
    if (pause.isPending) {
      return 'Working…';
    }
    if (encounter.is_paused) {
      return 'Unpause';
    }
    return 'Pause';
  };

  return (
    <div
      className="space-y-3 rounded-md border border-border bg-card p-3"
      data-testid="gm-encounter-controls"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        GM Controls
      </p>

      <div className="flex flex-wrap gap-2">
        <AddOpponentDialog encounterId={encounter.id} positions={encounter.position_nodes ?? []} />
        <AddParticipantDialog encounterId={encounter.id} />
        <Button
          size="sm"
          variant="outline"
          onClick={handlePause}
          disabled={pause.isPending}
          data-testid="pause-toggle-btn"
        >
          {renderPause()}
        </Button>
      </div>

      <EncounterSettingsRow encounter={encounter} />

      {isManual && (canBegin || canResolve) && (
        <div className="flex gap-2">
          {canBegin && (
            <Button
              size="sm"
              onClick={handleBeginRound}
              disabled={beginRound.isPending}
              data-testid="begin-round-btn"
            >
              {beginRound.isPending ? 'Beginning…' : 'Begin Round'}
            </Button>
          )}
          {canResolve && (
            <Button
              size="sm"
              onClick={handleResolveRound}
              disabled={resolveRound.isPending}
              data-testid="resolve-round-btn"
            >
              {resolveRound.isPending ? 'Resolving…' : 'Resolve Round'}
            </Button>
          )}
        </div>
      )}

      {encounter.participants.length > 0 && (
        <div className="space-y-1" data-testid="gm-participants-list">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Participants</p>
          {encounter.participants.map((p) => (
            <div
              key={p.id}
              className="flex items-center justify-between text-xs"
              data-testid={`gm-participant-row-${p.id}`}
            >
              <span>{p.character_name}</span>
              <button
                type="button"
                className="text-destructive hover:underline disabled:opacity-50"
                onClick={() => handleRemove(p.id)}
                disabled={removeParticipant.isPending}
                data-testid={`remove-participant-btn-${p.id}`}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {activeOpponents.length > 0 && (
        <div className="space-y-1" data-testid="gm-opponents-list">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Opponents</p>
          {activeOpponents.map((o) => (
            <div
              key={o.id}
              className="flex items-center justify-between text-xs"
              data-testid={`gm-opponent-row-${o.id}`}
            >
              <span>{o.name}</span>
              <button
                type="button"
                className="text-destructive hover:underline disabled:opacity-50"
                onClick={() => handleRemoveOpponent(o.id)}
                disabled={removeOpponent.isPending}
                data-testid={`remove-opponent-btn-${o.id}`}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Encounter settings row (#3383): stakes/risk/pace/timer/escalation, changeable
// mid-encounter. A persistent settings strip, not a one-shot dialog action;
// each control fires the mutation directly on change. The escalation curve
// (#3552) is GM-gated: the catalog fetch is only enabled for `encounter.is_gm`.
// ---------------------------------------------------------------------------

function EncounterSettingsRow({ encounter }: { encounter: EncounterDetail }) {
  const updateSettings = useUpdateEncounterSettings(encounter.id);
  const curves = useEscalationCurves(encounter.is_gm);
  const [timerDraft, setTimerDraft] = useState(String(encounter.pace_timer_minutes));
  const curveValue =
    encounter.escalation_curve == null ? NONE_CURVE : String(encounter.escalation_curve);

  // Keep the draft in sync when the server value changes from elsewhere
  // (another GM's edit, or our own mutation's refetch) — cheap and avoids a
  // stale display after a concurrent edit.
  useEffect(() => {
    setTimerDraft(String(encounter.pace_timer_minutes));
  }, [encounter.pace_timer_minutes]);

  function handleError(err: Error) {
    toast.error(err.message || 'Failed to update encounter settings.');
  }

  function handleStakesChange(value: string) {
    updateSettings.mutate({ stakesLevel: value as StakesLevel }, { onError: handleError });
  }

  function handleRiskChange(value: string) {
    updateSettings.mutate({ riskLevel: value as RiskLevel }, { onError: handleError });
  }

  function handlePaceChange(value: string) {
    updateSettings.mutate({ paceMode: value as PaceMode }, { onError: handleError });
  }

  function handleCurveChange(value: string) {
    const escalationCurve = value === NONE_CURVE ? null : Number(value);
    updateSettings.mutate({ escalationCurve }, { onError: handleError });
  }

  function commitTimer() {
    const minutes = Number(timerDraft);
    if (!Number.isInteger(minutes) || minutes < 1) {
      setTimerDraft(String(encounter.pace_timer_minutes));
      return;
    }
    if (minutes === encounter.pace_timer_minutes) return;
    updateSettings.mutate({ paceTimerMinutes: minutes }, { onError: handleError });
  }

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-muted/20 p-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Settings</p>
      <div className="flex flex-wrap gap-2">
        <div className="space-y-1">
          <Label className="text-[10px]">Stakes</Label>
          <Select value={encounter.stakes_level} onValueChange={handleStakesChange}>
            <SelectTrigger data-testid="encounter-stakes-select" className="h-8 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STAKES_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value} className="text-xs">
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-[10px]">Risk</Label>
          <Select value={encounter.risk_level} onValueChange={handleRiskChange}>
            <SelectTrigger data-testid="encounter-risk-select" className="h-8 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RISK_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value} className="text-xs">
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-[10px]">Pace</Label>
          <Select value={encounter.pace_mode} onValueChange={handlePaceChange}>
            <SelectTrigger data-testid="encounter-pace-select" className="h-8 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PACE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value} className="text-xs">
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-[10px]">Escalation</Label>
          <Select value={curveValue} onValueChange={handleCurveChange}>
            <SelectTrigger data-testid="encounter-curve-select" className="h-8 w-40 text-xs">
              <SelectValue>
                {encounter.escalation_curve == null
                  ? 'None (does not escalate)'
                  : (encounter.escalation_curve_name ?? 'Curve')}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE_CURVE} className="text-xs">
                None (does not escalate)
              </SelectItem>
              {(curves.data ?? []).map((curve) => (
                <SelectItem key={curve.id} value={String(curve.id)} className="text-xs">
                  {curve.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {encounter.pace_mode === 'timed' && (
          <div className="space-y-1">
            <Label htmlFor="encounter-timer-input" className="text-[10px]">
              Timer (min)
            </Label>
            <Input
              id="encounter-timer-input"
              type="number"
              min={1}
              className="h-8 w-20 text-xs"
              value={timerDraft}
              onChange={(e) => setTimerDraft(e.target.value)}
              onBlur={commitTimer}
              data-testid="encounter-timer-input"
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add opponent dialog
// ---------------------------------------------------------------------------

// Native <select> styling shared by the bestiary picker below — mirrors
// GMAdjudicationPanel's SELECT_CLASS (Call Check CheckType picker pattern,
// #3424 spec), not re-exported from there since it's a one-line Tailwind
// string, not worth a shared module yet.
const NATIVE_SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

function AddOpponentDialog({
  encounterId,
  positions,
}: {
  encounterId: number;
  positions: PositionNode[];
}) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" data-testid="add-opponent-trigger">
          Add Opponent
        </Button>
      </DialogTrigger>
      <DialogContent data-testid="add-opponent-dialog">
        <DialogHeader>
          <DialogTitle>Add Opponent</DialogTitle>
        </DialogHeader>
        {/* Two modes (#3424): Freehand (formula-scaled, on-the-spot invention)
            stays the default; From Bestiary spawns an authored CreatureTemplate
            with its cloned phases/break-bar intact. Each tab's form only mounts
            (and only calls its own hooks) while active — Radix Tabs unmounts
            inactive content by default. */}
        <Tabs defaultValue="freehand">
          <TabsList>
            <TabsTrigger value="freehand" data-testid="add-opponent-mode-freehand">
              Freehand
            </TabsTrigger>
            <TabsTrigger value="bestiary" data-testid="add-opponent-mode-bestiary">
              From Bestiary
            </TabsTrigger>
          </TabsList>
          <TabsContent value="freehand">
            <FreehandOpponentForm
              encounterId={encounterId}
              positions={positions}
              onDone={() => setOpen(false)}
            />
          </TabsContent>
          <TabsContent value="bestiary">
            <BestiarySpawnForm
              encounterId={encounterId}
              positions={positions}
              onDone={() => setOpen(false)}
            />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function FreehandOpponentForm({
  encounterId,
  positions,
  onDone,
}: {
  encounterId: number;
  positions: PositionNode[];
  onDone: () => void;
}) {
  const [name, setName] = useState('');
  const [tier, setTier] = useState<OpponentTier>('mook');
  const [threatPoolId, setThreatPoolId] = useState<number | null>(null);
  const [positionId, setPositionId] = useState<number | null>(null);

  const { data: pools = [] } = useThreatPools();
  const { data: defaults } = useOpponentDefaults(encounterId, tier);
  const { mutate, isPending, error, isError } = useAddOpponent(encounterId);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || threatPoolId === null) return;
    mutate(
      { name: name.trim(), tier, threatPoolId, positionId },
      {
        onSuccess: onDone,
        onError: () => {
          /* surfaced inline below via isError */
        },
      }
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="opponent-name">Name</Label>
        <Input
          id="opponent-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Goblin Raider"
          data-testid="add-opponent-name"
        />
      </div>

      <div className="space-y-1.5">
        <Label>Tier</Label>
        <Select value={tier} onValueChange={(v) => setTier(v as OpponentTier)}>
          <SelectTrigger data-testid="add-opponent-tier-select">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIER_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {defaults && (
        <div
          className="rounded border border-border bg-muted/30 p-2 text-xs"
          data-testid="add-opponent-defaults-preview"
        >
          <p>
            Health {defaults.max_health} · Soak {defaults.soak_value}
            {defaults.probing_threshold !== null ? ` · Probing ${defaults.probing_threshold}` : ''}
          </p>
          {!defaults.stakes_ok && (
            <p className="mt-1 text-amber-500" data-testid="add-opponent-stakes-warning">
              {defaults.stakes_message}
            </p>
          )}
        </div>
      )}

      <div className="space-y-1.5">
        <Label>Threat Pool</Label>
        <Select
          value={threatPoolId !== null ? String(threatPoolId) : ''}
          onValueChange={(v) => setThreatPoolId(Number(v))}
        >
          <SelectTrigger data-testid="add-opponent-pool-select">
            <SelectValue placeholder="Select a threat pool…" />
          </SelectTrigger>
          <SelectContent>
            {pools.map((p) => (
              <SelectItem key={p.id} value={String(p.id)}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {positions.length > 0 && (
        <div className="space-y-1.5">
          <Label>Position (optional)</Label>
          <Select
            value={positionId !== null ? String(positionId) : ''}
            onValueChange={(v) => setPositionId(v === '' ? null : Number(v))}
          >
            <SelectTrigger data-testid="add-opponent-position-select">
              <SelectValue placeholder="Unplaced" />
            </SelectTrigger>
            <SelectContent>
              {positions.map((pos) => (
                <SelectItem key={pos.id} value={String(pos.id)}>
                  {pos.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {isError && (
        <p role="alert" className="text-sm text-destructive" data-testid="add-opponent-error">
          {error instanceof Error ? error.message : 'Failed to add opponent.'}
        </p>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone} disabled={isPending}>
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={isPending || !name.trim() || threatPoolId === null}
          data-testid="add-opponent-submit"
        >
          {isPending ? 'Adding…' : 'Add'}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Spawn from bestiary (#3424) — the authored-CreatureTemplate sibling of the
// freehand form above. Rides the generic REGISTRY dispatch seam
// (spawn_creature) rather than a bespoke REST verb, so it needs the caller's
// own characterId (mirrors GMAdjudicationPanel's active-character resolution).
// ---------------------------------------------------------------------------

function BestiarySpawnForm({
  encounterId,
  positions,
  onDone,
}: {
  encounterId: number;
  positions: PositionNode[];
  onDone: () => void;
}) {
  const [search, setSearch] = useState('');
  const [templateName, setTemplateName] = useState<string | null>(null);
  const [positionId, setPositionId] = useState<number | null>(null);

  const { data: templates = [] } = useCreatureTemplates(search);

  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const { mutate, isPending, error, isError } = useSpawnCreature(encounterId, characterId ?? 0);

  const canSubmit = templateName !== null && characterId !== null && !isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || templateName === null) return;
    mutate(
      { template: templateName, positionId },
      {
        onSuccess: (result) => {
          if (isDispatchFailure(result)) {
            toast.error(result.message ?? 'Failed to spawn creature.');
            return;
          }
          onDone();
        },
        onError: () => {
          /* surfaced inline below via isError */
        },
      }
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="spawn-creature-search">Creature</Label>
        <Input
          id="spawn-creature-search"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setTemplateName(null);
          }}
          placeholder="Search the bestiary…"
          data-testid="spawn-creature-search"
        />
        <select
          className={NATIVE_SELECT_CLASS}
          value={templateName ?? ''}
          onChange={(e) => setTemplateName(e.target.value || null)}
          data-testid="spawn-creature-select"
        >
          <option value="">Select a creature…</option>
          {templates.map((t) => (
            <option key={t.id} value={t.name}>
              {t.name} ({t.tier}
              {t.has_phases ? ', phases' : ''})
            </option>
          ))}
        </select>
      </div>

      {positions.length > 0 && (
        <div className="space-y-1.5">
          <Label>Position (optional)</Label>
          <Select
            value={positionId !== null ? String(positionId) : ''}
            onValueChange={(v) => setPositionId(v === '' ? null : Number(v))}
          >
            <SelectTrigger data-testid="spawn-creature-position-select">
              <SelectValue placeholder="Unplaced" />
            </SelectTrigger>
            <SelectContent>
              {positions.map((pos) => (
                <SelectItem key={pos.id} value={String(pos.id)}>
                  {pos.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {characterId === null && (
        <p className="text-xs text-muted-foreground" data-testid="spawn-creature-no-character">
          No active character to spawn as.
        </p>
      )}

      {isError && (
        <p role="alert" className="text-sm text-destructive" data-testid="spawn-creature-error">
          {error instanceof Error ? error.message : 'Failed to spawn creature.'}
        </p>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone} disabled={isPending}>
          Cancel
        </Button>
        <Button type="submit" disabled={!canSubmit} data-testid="spawn-creature-submit">
          {isPending ? 'Spawning…' : 'Spawn'}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Add participant (PC) dialog
// ---------------------------------------------------------------------------

function AddParticipantDialog({ encounterId }: { encounterId: number }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<{ characterSheetId: number; name: string } | null>(null);
  const { results } = usePersonaSearch(query);
  const { mutate, isPending, error, isError } = useAddParticipant(encounterId);

  function reset() {
    setQuery('');
    setSelected(null);
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) reset();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (selected === null) return;
    mutate(
      { characterSheetId: selected.characterSheetId },
      { onSuccess: () => handleOpenChange(false) }
    );
  }

  const showResults = results.length > 0 && (selected === null || selected.name !== query);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" data-testid="add-participant-trigger">
          Add PC
        </Button>
      </DialogTrigger>
      <DialogContent data-testid="add-participant-dialog">
        <DialogHeader>
          <DialogTitle>Add PC</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="participant-search">Character</Label>
            <Input
              id="participant-search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelected(null);
              }}
              placeholder="Search for a character…"
              data-testid="add-participant-search"
            />
            {showResults && (
              <ul className="rounded border border-border" data-testid="add-participant-results">
                {results.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="w-full px-2 py-1 text-left text-xs hover:bg-muted disabled:opacity-50"
                      disabled={p.character_sheet === null}
                      onClick={() => {
                        if (p.character_sheet === null) return;
                        setSelected({ characterSheetId: p.character_sheet, name: p.name });
                        setQuery(p.name);
                      }}
                      data-testid={`add-participant-option-${p.id}`}
                    >
                      {p.name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {isError && (
            <p
              role="alert"
              className="text-sm text-destructive"
              data-testid="add-participant-error"
            >
              {error instanceof Error ? error.message : 'Failed to add participant.'}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isPending || selected === null}
              data-testid="add-participant-submit"
            >
              {isPending ? 'Adding…' : 'Add'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Start lethal duel dialog (#3068)
// ---------------------------------------------------------------------------

function StartLethalDuelDialog({ sceneId }: { sceneId: number }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<{ characterSheetId: number; name: string } | null>(null);
  const [opponentName, setOpponentName] = useState('');
  const [tier, setTier] = useState<LethalDuelTier>('elite');
  const [threatPoolId, setThreatPoolId] = useState<number | null>(null);

  const { results } = usePersonaSearch(query);
  const { data: pools = [] } = useThreatPools();
  const { mutate, isPending, error, isError } = useProposeLethalDuel();

  function reset() {
    setQuery('');
    setSelected(null);
    setOpponentName('');
    setTier('elite');
    setThreatPoolId(null);
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) reset();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (selected === null || !opponentName.trim() || threatPoolId === null) return;
    mutate(
      {
        sceneId,
        challengedSheetId: selected.characterSheetId,
        opponentName: opponentName.trim(),
        tier,
        threatPoolId,
      },
      {
        onSuccess: () => {
          toast.success(`Lethal duel proposed — awaiting ${selected.name}'s response.`);
          handleOpenChange(false);
        },
        onError: () => {
          /* surfaced inline below via isError */
        },
      }
    );
  }

  const showResults = results.length > 0 && (selected === null || selected.name !== query);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" variant="destructive" data-testid="start-lethal-duel-trigger">
          Start Lethal Duel
        </Button>
      </DialogTrigger>
      <DialogContent data-testid="start-lethal-duel-dialog">
        <DialogHeader>
          <DialogTitle>Start Lethal Duel</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Proposes a climactic one-on-one fight to the death against a significant named antagonist.
          The targeted player must accept before the duel begins — this does not force the fight
          open.
        </p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="lethal-duel-target-search">Target PC</Label>
            <Input
              id="lethal-duel-target-search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelected(null);
              }}
              placeholder="Search for a character…"
              data-testid="lethal-duel-target-search"
            />
            {showResults && (
              <ul className="rounded border border-border" data-testid="lethal-duel-target-results">
                {results.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="w-full px-2 py-1 text-left text-xs hover:bg-muted disabled:opacity-50"
                      disabled={p.character_sheet === null}
                      onClick={() => {
                        if (p.character_sheet === null) return;
                        setSelected({ characterSheetId: p.character_sheet, name: p.name });
                        setQuery(p.name);
                      }}
                      data-testid={`lethal-duel-target-option-${p.id}`}
                    >
                      {p.name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="lethal-duel-opponent-name">Antagonist name</Label>
            <Input
              id="lethal-duel-opponent-name"
              value={opponentName}
              onChange={(e) => setOpponentName(e.target.value)}
              placeholder="The Widow Ashgrave"
              data-testid="lethal-duel-opponent-name"
            />
          </div>

          <div className="space-y-1.5">
            <Label>Tier</Label>
            <Select value={tier} onValueChange={(v) => setTier(v as LethalDuelTier)}>
              <SelectTrigger data-testid="lethal-duel-tier-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LETHAL_TIER_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Threat Pool</Label>
            <Select
              value={threatPoolId !== null ? String(threatPoolId) : ''}
              onValueChange={(v) => setThreatPoolId(Number(v))}
            >
              <SelectTrigger data-testid="lethal-duel-pool-select">
                <SelectValue placeholder="Select a threat pool…" />
              </SelectTrigger>
              <SelectContent>
                {pools.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isError && (
            <p role="alert" className="text-sm text-destructive" data-testid="lethal-duel-error">
              {error instanceof Error ? error.message : 'Failed to propose the lethal duel.'}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={
                isPending || selected === null || !opponentName.trim() || threatPoolId === null
              }
              data-testid="lethal-duel-submit"
            >
              {isPending ? 'Proposing…' : 'Propose Duel'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
