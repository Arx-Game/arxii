/**
 * CombatantsList — rail section showing PC and NPC combatant rows.
 *
 * PC rows: PersonaAvatar resolving the participant's primary-persona thumbnail
 *   (serializer `thumbnail_url` / `thumbnail_media_url`; resolved server-side with
 *   select_related, no per-PC query), falling back to a name-derived initial letter.
 *   Source: EncounterDetail.participants.
 *
 * NPC rows: PersonaAvatar resolving the opponent's persona thumbnail (serializer
 *   `thumbnail_url` / `thumbnail_media_url`), falling back to a name-derived initial
 *   letter when the opponent has no persona. Source: EncounterDetail.opponents.
 *
 * NPCs are visually distinct from PCs via a destructive-tinted border + background.
 *
 * Condition badges: each row renders its `active_conditions` as ConditionBadge
 *   chips that deep-link to the shared condition-detail modal on click.
 *
 * Opponent click-menu (#3381): each opponent row carries a kebab-trigger
 * dropdown (Radix, mirrors PersonaContextMenu.tsx's pattern) offering
 * Taunt/Demoralize/Parley — a kebab icon rather than the row itself as the
 * trigger, so it doesn't collide with the condition-badge deep-link already
 * on the row. Only rendered when the caller passes `canDeclareManeuvers`
 * (derived by CombatTurnPanel from `is_participant && status === 'declaring'`
 * — GM/observer rows never get the menu) and a `characterId` to dispatch as.
 *
 * Engagement-lock badge (#3386): an opponent row shows "Locked: <PC name>" when
 * an active EngagementLock names them. The kebab menu additionally offers
 * "Engage in a duel" (hidden while anyone holds the lock) and "Disengage"
 * (only when the viewer's own participant holds it) since #3447 — dispatching
 * combat_engage/combat_disengage through the same generic registry seam.
 *
 * Phase 8, Task 8.3 — unified-combat-ui plan.
 */

import { MoreVertical } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConditionBadge } from '../components/ConditionBadge';
import { useRegistryDispatch } from '../queries';
import { isDispatchFailure } from '../types';
import type { EncounterDetail, Participant, Opponent } from '../types';
import type { components } from '@/generated/api';

type ConditionInstance = components['schemas']['ConditionInstance'];

// ---------------------------------------------------------------------------
// ConditionRow — flex row of condition badges for a combatant
// ---------------------------------------------------------------------------

interface ConditionRowProps {
  /**
   * active_conditions is typed loosely as `{[key: string]: unknown}[]` on the
   * generated Participant/Opponent schemas (it's a SerializerMethodField); each
   * entry is really a ConditionInstance. Cast at the boundary.
   */
  conditions?: { [key: string]: unknown }[];
}

function ConditionRow({ conditions }: ConditionRowProps) {
  if (!conditions || conditions.length === 0) {
    return null;
  }
  // Backend already orders by display_priority desc; be defensive and re-sort.
  const sorted = [...(conditions as ConditionInstance[])].sort(
    (a, b) => b.display_priority - a.display_priority
  );
  return (
    <div className="mt-1 flex flex-wrap gap-1" data-testid="condition-row">
      {sorted.map((condition) => (
        <ConditionBadge key={condition.id} condition={condition} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CombatantsListProps {
  encounter: EncounterDetail;
  /** Whether the section is collapsed. Controlled by parent (Task 8.6). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  /**
   * The viewer's character id — required to dispatch a maneuver from the
   * opponent click-menu (#3381). Omitted/0 for a GM/observer, who never gets
   * the menu regardless (see `canDeclareManeuvers`).
   */
  characterId?: number;
  /**
   * True when the viewer may declare a maneuver this round — mirrors
   * `isDeclaringPhase` in YourTurn.tsx (`encounter.status === 'declaring'`)
   * ANDed with `encounter.is_participant`. Threaded down from CombatTurnPanel
   * (the shared parent that mounts both YourTurn and CombatantsList) rather
   * than re-derived here, per #3381's leak-analysis: a GM/observer row must
   * never render the menu.
   */
  canDeclareManeuvers?: boolean;
}

// ---------------------------------------------------------------------------
// HP mini-bar
// ---------------------------------------------------------------------------

interface HpBarProps {
  health: number | null;
  maxHealth: number | null;
  className?: string;
}

function HpBar({ health, maxHealth, className }: HpBarProps) {
  const pct =
    health !== null && maxHealth !== null && maxHealth > 0
      ? Math.min(100, (health / maxHealth) * 100)
      : 0;
  const isWounded = health !== null && maxHealth !== null && health / maxHealth < 0.5;

  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-muted', className)}>
      <div
        className={cn(
          'h-full rounded-full transition-all',
          isWounded ? 'bg-amber-500' : 'bg-emerald-500'
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// ParticipantRow — one PC combatant row
// ---------------------------------------------------------------------------

interface ParticipantRowProps {
  participant: Participant;
  /** Name of the opponent this PC is engagement-locked to, if any (#3555). */
  lockedToName?: string;
}

function ParticipantRow({ participant, lockedToName }: ParticipantRowProps) {
  return (
    <div
      className="flex items-center gap-2 rounded p-1.5 hover:bg-accent/30"
      data-testid={`participant-row-${participant.id}`}
    >
      {/* Avatar — portrait resolves via the PC's primary persona thumbnail;
       * falls back to an initial-letter avatar when there is none (#630).
       */}
      <PersonaAvatar
        source={{
          name: participant.character_name,
          thumbnailUrl: participant.thumbnail_url,
          thumbnailMediaUrl: participant.thumbnail_media_url,
        }}
        size="sm"
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1">
          <p className="truncate text-xs font-medium text-foreground">
            {participant.character_name}
          </p>
          {participant.current_position && (
            <span
              data-testid="position-badge"
              className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground"
            >
              {participant.current_position.name}
            </span>
          )}
          {lockedToName && (
            <span
              data-testid="engagement-lock-badge"
              className="shrink-0 rounded bg-primary/10 px-1 py-0.5 text-[10px] text-primary"
            >
              Locked: {lockedToName}
            </span>
          )}
        </div>
        {/* HP mini-bar */}
        <HpBar health={participant.health} maxHealth={participant.max_health} className="mt-0.5" />
        {/* Condition badges — deep-link to the condition-detail modal on click. */}
        <ConditionRow conditions={participant.active_conditions} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// OpponentRow — one NPC combatant row
// ---------------------------------------------------------------------------

interface OpponentRowProps {
  opponent: Opponent;
  encounterId: number;
  characterId?: number;
  canDeclareManeuvers?: boolean;
  /** Name of the PC this opponent is engagement-locked to, if any (#3386). */
  lockedToName?: string;
  /** True when the active lock on this opponent belongs to the viewer (#3447). */
  lockedToViewer?: boolean;
}

/** One opponent-targeted maneuver offered by the click-menu (#3381). */
const OPPONENT_MANEUVERS: {
  key: 'combat_taunt' | 'combat_demoralize' | 'combat_parley';
  label: string;
}[] = [
  { key: 'combat_taunt', label: 'Taunt' },
  { key: 'combat_demoralize', label: 'Demoralize' },
  { key: 'combat_parley', label: 'Parley' },
];

function OpponentRow({
  opponent,
  encounterId,
  characterId,
  canDeclareManeuvers = false,
  lockedToName,
  lockedToViewer = false,
}: OpponentRowProps) {
  const showMenu = canDeclareManeuvers && characterId != null;
  const { mutateAsync, isPending } = useRegistryDispatch(encounterId, characterId ?? 0);

  async function handleManeuver(registryKey: string, label: string) {
    try {
      const result = await mutateAsync({ registryKey, kwargs: { opponent_id: opponent.id } });
      if (isDispatchFailure(result)) {
        toast.error(result.message ?? `Failed to ${label.toLowerCase()}.`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Failed to ${label.toLowerCase()}.`);
    }
  }

  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded border border-destructive/30 bg-destructive/5 p-1.5',
        'hover:bg-destructive/10'
      )}
      data-testid={`opponent-row-${opponent.id}`}
    >
      {/* Avatar — portrait resolves via the opponent's persona thumbnail; falls
       * back to an initial-letter avatar when the opponent is persona-less.
       */}
      <PersonaAvatar
        source={{
          name: opponent.name,
          thumbnailUrl: opponent.thumbnail_url,
          thumbnailMediaUrl: opponent.thumbnail_media_url,
        }}
        size="sm"
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1">
          <p className="truncate text-xs font-medium text-foreground">{opponent.name}</p>
          {opponent.current_position && (
            <span
              data-testid="position-badge"
              className="shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground"
            >
              {opponent.current_position.name}
            </span>
          )}
          {lockedToName && (
            <span
              data-testid="engagement-lock-badge"
              className="shrink-0 rounded bg-primary/10 px-1 py-0.5 text-[10px] text-primary"
            >
              Locked: {lockedToName}
            </span>
          )}
        </div>
        {/* HP mini-bar */}
        <HpBar health={opponent.health} maxHealth={opponent.max_health} className="mt-0.5" />
        {/* Condition badges — deep-link to the condition-detail modal on click. */}
        <ConditionRow conditions={opponent.active_conditions} />
      </div>

      {/* Opponent click-menu (#3381) — Taunt/Demoralize/Parley. A kebab trigger
       * (not the row itself) avoids colliding with the condition-badge deep-link. */}
      {showMenu && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              data-testid={`opponent-menu-trigger-${opponent.id}`}
              aria-label={`Actions on ${opponent.name}`}
              className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent/50 hover:text-foreground"
            >
              <MoreVertical className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {OPPONENT_MANEUVERS.map(({ key, label }) => (
              <DropdownMenuItem
                key={key}
                disabled={isPending}
                data-testid={`opponent-${key}-${opponent.id}`}
                onClick={() => {
                  handleManeuver(key, label).catch(() => {});
                }}
              >
                {label}
              </DropdownMenuItem>
            ))}
            {/* Engagement lock (#2020/#3447) — the web half #3396 deferred.
             * Engage offers when nobody holds the lock; Disengage when the
             * viewer holds it. A locked-to-someone-else opponent gets neither
             * (the backend would reject Engage with its own message anyway). */}
            {!lockedToName && (
              <DropdownMenuItem
                disabled={isPending}
                data-testid={`opponent-combat_engage-${opponent.id}`}
                onClick={() => {
                  handleManeuver('combat_engage', 'Engage').catch(() => {});
                }}
              >
                Engage in a duel
              </DropdownMenuItem>
            )}
            {lockedToViewer && (
              <DropdownMenuItem
                disabled={isPending}
                data-testid={`opponent-combat_disengage-${opponent.id}`}
                onClick={() => {
                  handleManeuver('combat_disengage', 'Disengage').catch(() => {});
                }}
              >
                Disengage
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CombatantsList
// ---------------------------------------------------------------------------

export function CombatantsList({
  encounter,
  collapsed = false,
  onToggleCollapse,
  characterId,
  canDeclareManeuvers = false,
}: CombatantsListProps) {
  const { participants, opponents, engagement_locks: engagementLocks } = encounter;

  // Map opponent id -> locked PC's display name (#3386, read-only visibility),
  // and participant id -> locked opponent's name for the PC row (#3555).
  const lockedOpponentNames = new Map<number, string>();
  const lockedParticipantNames = new Map<number, string>();
  for (const lock of engagementLocks ?? []) {
    const pc = participants.find((p) => p.id === lock.participant_id);
    if (pc) {
      lockedOpponentNames.set(lock.opponent_id, pc.character_name);
    }
    const npc = opponents.find((o) => o.id === lock.opponent_id);
    if (npc) {
      lockedParticipantNames.set(lock.participant_id, npc.name);
    }
  }

  // #3447 — the viewer's own participant (CharacterSheet shares ObjectDB's pk,
  // so character_sheet_id compares directly against the characterId prop) and
  // the opponent ids whose active lock the viewer holds, for the Disengage item.
  const viewerParticipantId =
    characterId != null
      ? (participants.find((p) => p.character_sheet_id === characterId)?.id ?? null)
      : null;
  const viewerLockedOpponentIds = new Set<number>(
    (engagementLocks ?? [])
      .filter((lock) => viewerParticipantId !== null && lock.participant_id === viewerParticipantId)
      .map((lock) => lock.opponent_id)
  );

  return (
    <div className="rounded-md border border-border bg-card" data-testid="combatants-list-section">
      {/* Section header */}
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={!collapsed}
        data-testid="combatants-list-toggle"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Combatants
        </span>
        <span
          className={cn(
            'text-muted-foreground transition-transform',
            collapsed ? '-rotate-90' : 'rotate-0'
          )}
          aria-hidden="true"
        >
          ▾
        </span>
      </button>

      {/* Content */}
      {!collapsed && (
        <div className="space-y-2 border-t border-border px-3 py-2">
          {/* PC section */}
          {participants.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Players
              </p>
              {participants.map((p) => (
                <ParticipantRow
                  key={p.id}
                  participant={p}
                  lockedToName={lockedParticipantNames.get(p.id)}
                />
              ))}
            </div>
          )}

          {/* NPC section */}
          {opponents.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Opponents
              </p>
              {opponents.map((o) => (
                <OpponentRow
                  key={o.id}
                  opponent={o}
                  encounterId={encounter.id}
                  characterId={characterId}
                  canDeclareManeuvers={canDeclareManeuvers}
                  lockedToName={lockedOpponentNames.get(o.id)}
                  lockedToViewer={viewerLockedOpponentIds.has(o.id)}
                />
              ))}
            </div>
          )}

          {participants.length === 0 && opponents.length === 0 && (
            <p className="text-xs text-muted-foreground" data-testid="combatants-empty">
              No combatants yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
