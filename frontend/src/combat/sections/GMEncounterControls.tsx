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
 */

import { useState } from 'react';
import type React from 'react';
import { toast } from 'sonner';
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
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import type { OpponentTier, PaceMode } from '../api';
import {
  useAddOpponent,
  useAddParticipant,
  useBeginRound,
  useCreateEncounter,
  useOpponentDefaults,
  usePauseEncounter,
  useRemoveParticipant,
  useResolveRound,
  useThreatPools,
} from '../queries';
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

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export function GMEncounterControls({ sceneId, encounter, viewerCanGm }: GMEncounterControlsProps) {
  if (!encounter) {
    if (!viewerCanGm) return null;
    return <StartEncounterCard sceneId={sceneId} />;
  }
  if (!encounter.is_gm) return null;
  return <ActiveGMControls encounter={encounter} />;
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

  // Manual round control is only meaningful in MANUAL pace — TIMED resolves on
  // its own timer, READY resolves once every participant readies up.
  const isManual = encounter.pace_mode === 'manual';
  const canBegin = isManual && encounter.status === 'between_rounds';
  const canResolve = isManual && encounter.status === 'declaring';

  function handleRemove(participantId: number) {
    removeParticipant.mutate(participantId, {
      onError: (err: Error) => toast.error(err.message || 'Failed to remove participant.'),
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
          {pause.isPending ? 'Working…' : encounter.is_paused ? 'Unpause' : 'Pause'}
        </Button>
      </div>

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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add opponent dialog
// ---------------------------------------------------------------------------

function AddOpponentDialog({
  encounterId,
  positions,
}: {
  encounterId: number;
  positions: PositionNode[];
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [tier, setTier] = useState<OpponentTier>('mook');
  const [threatPoolId, setThreatPoolId] = useState<number | null>(null);
  const [positionId, setPositionId] = useState<number | null>(null);

  const { data: pools = [] } = useThreatPools();
  // Only fetch the scaling preview while the dialog is open — avoids a
  // background poll for a picker nobody's looking at.
  const { data: defaults } = useOpponentDefaults(encounterId, open ? tier : null);
  const { mutate, isPending, error, isError } = useAddOpponent(encounterId);

  function reset() {
    setName('');
    setTier('mook');
    setThreatPoolId(null);
    setPositionId(null);
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) reset();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || threatPoolId === null) return;
    mutate(
      { name: name.trim(), tier, threatPoolId, positionId },
      {
        onSuccess: () => handleOpenChange(false),
        onError: () => {
          /* surfaced inline below via isError */
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" data-testid="add-opponent-trigger">
          Add Opponent
        </Button>
      </DialogTrigger>
      <DialogContent data-testid="add-opponent-dialog">
        <DialogHeader>
          <DialogTitle>Add Opponent</DialogTitle>
        </DialogHeader>
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
                {defaults.probing_threshold !== null
                  ? ` · Probing ${defaults.probing_threshold}`
                  : ''}
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
              disabled={isPending || !name.trim() || threatPoolId === null}
              data-testid="add-opponent-submit"
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
