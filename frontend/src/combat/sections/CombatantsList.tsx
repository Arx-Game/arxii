/**
 * CombatantsList — rail section showing PC and NPC combatant rows.
 *
 * PC rows: PersonaAvatar (initial-letter only — fetching per-participant persona
 *   thumbnail would require a separate query per PC; deferred to a follow-up task).
 *   Source: EncounterDetail.participants.
 *
 * NPC rows: PersonaAvatar (initial-letter only — CombatOpponent has no Persona FK;
 *   v1 uses name-derived initial letter, a portrait FK addition is a future task).
 *   Source: EncounterDetail.opponents.
 *
 * NPCs are visually distinct from PCs via a destructive-tinted border + background.
 *
 * Condition icon row: placeholder until conditions are surfaced in the encounter
 *   payload. TODO(conditions): wire real condition data when available.
 *
 * Phase 8, Task 8.3 — unified-combat-ui plan.
 */

import { cn } from '@/lib/utils';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import type { EncounterDetail, Participant, Opponent } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CombatantsListProps {
  encounter: EncounterDetail;
  /** Whether the section is collapsed. Controlled by parent (Task 8.6). */
  collapsed?: boolean;
  onToggleCollapse?: () => void;
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
}

function ParticipantRow({ participant }: ParticipantRowProps) {
  return (
    <div
      className="flex items-center gap-2 rounded p-1.5 hover:bg-accent/30"
      data-testid={`participant-row-${participant.id}`}
    >
      {/* Avatar — initial-letter only (v1 simplification: per-participant persona
       * thumbnail fetch would require a separate query per PC).
       * TODO(avatars): fetch primary persona thumbnail_media_url per participant
       * once the encounter detail serializer exposes character_sheet_id.
       */}
      <PersonaAvatar source={{ name: participant.character_name }} size="sm" />

      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-foreground">{participant.character_name}</p>
        {/* HP mini-bar */}
        <HpBar health={participant.health} maxHealth={participant.max_health} className="mt-0.5" />
        {/* Condition icon row — placeholder until conditions in encounter payload.
         * TODO(conditions): render condition icons when encounter detail exposes them.
         */}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// OpponentRow — one NPC combatant row
// ---------------------------------------------------------------------------

interface OpponentRowProps {
  opponent: Opponent;
}

function OpponentRow({ opponent }: OpponentRowProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded border border-destructive/30 bg-destructive/5 p-1.5',
        'hover:bg-destructive/10'
      )}
      data-testid={`opponent-row-${opponent.id}`}
    >
      {/* Avatar — initial-letter only. CombatOpponent has no Persona FK in v1.
       * TODO(avatars): add portrait FK to CombatOpponent and resolve here.
       */}
      <PersonaAvatar source={{ name: opponent.name }} size="sm" />

      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-foreground">{opponent.name}</p>
        {/* HP mini-bar */}
        <HpBar health={opponent.health} maxHealth={opponent.max_health} className="mt-0.5" />
      </div>
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
}: CombatantsListProps) {
  const { participants, opponents } = encounter;

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
                <ParticipantRow key={p.id} participant={p} />
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
                <OpponentRow key={o.id} opponent={o} />
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
