/**
 * Marginalia (#3477 Task 6) — the manuscript's always-visible side panels,
 * fed entirely from `fetchRoomDetail`'s payload: Exits (the one panel with
 * a real editor — chips open `ExitEditorDialog`, ⊕ opens the exit-mode
 * `AddDialog`; Art gained the second door in #3535 — `ArtDialog` via
 * `onOpenArt`), Ownership, People, Ambience, Places & Things, Law & Danger,
 * Secrets & Story, and Resonance.
 *
 * Every panel but Exits is read-only display here (matching the brief's
 * explicit ruling for Ambience — "shows counts only," T7 builds its real
 * editor — generalized to the rest: none of these systems has a builder
 * action to wire from this task, so a ⊕ row here would be a dead button).
 * Ownership's Deed/Tenants are "not tracked yet" rather than invented —
 * the room payload has no tenancy fields at all yet, only `is_public`
 * (Listing). Resonance reads `room.stats` for anything resonance-shaped;
 * none exists in the current payload, so it always shows the honest
 * "unresonant ground" fallback today — this stays forward-compatible
 * without fabricating data that isn't there.
 */
import type { ReactNode } from 'react';

import { PlateHead } from '@/components/folio';

import type { WorldBuilderComfort, WorldBuilderExitDetail, WorldBuilderRoom } from '../types';

export interface MarginaliaProps {
  room: WorldBuilderRoom;
  exits: WorldBuilderExitDetail[];
  comfort: WorldBuilderComfort;
  cluesCount: number;
  clueTriggersCount: number;
  onOpenExit: (exit: WorldBuilderExitDetail) => void;
  onAddExit: () => void;
  /** Opens the ArtDialog (#3535) — the second real door after Exits. */
  onOpenArt: () => void;
}

function Panel({
  label,
  count,
  children,
}: {
  label: string;
  count?: number | string;
  children: ReactNode;
}) {
  return (
    <div
      className="border-b pb-2 pt-2"
      data-testid={`marginalia-panel-${label.toLowerCase().replace(/[^a-z]+/g, '-')}`}
    >
      <PlateHead as="h4" className="mb-1 flex items-center gap-2">
        {label}
        {count !== undefined && (
          <span className="ml-auto font-normal tracking-normal text-muted-foreground">{count}</span>
        )}
      </PlateHead>
      {children}
    </div>
  );
}

function Kv({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-2 text-sm">
      <b className="font-medium">{term}</b>
      <span className="text-right text-muted-foreground">{children}</span>
    </div>
  );
}

export function Marginalia({
  room,
  exits,
  comfort,
  cluesCount,
  clueTriggersCount,
  onOpenExit,
  onAddExit,
  onOpenArt,
}: MarginaliaProps) {
  const resonanceStat = room.stats.find((stat) => stat.key.startsWith('resonance'));
  const dangerStats = room.stats.filter((stat) => stat.key === 'crime' || stat.key === 'order');
  const placeNames = room.places.map((p) => p.name).join(', ') || 'none';
  const featureLabel = room.feature
    ? `${room.feature.kind} · level ${room.feature.level}`
    : 'empty';

  return (
    <aside aria-label="Room marginalia" data-testid="marginalia" className="flex flex-col">
      <Panel label="Exits" count={exits.length}>
        <div className="flex flex-wrap gap-1" data-testid="exit-chips">
          {exits.map((exit) => (
            <button
              key={exit.id}
              type="button"
              className="border px-2 py-0.5 text-xs hover:bg-accent"
              onClick={() => onOpenExit(exit)}
              data-testid={`exit-chip-${exit.id}`}
            >
              {exit.name}
              {exit.kind === 'window' && ' ⊞'}
              {!exit.is_open && ' ⊘'}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="mt-1 text-left font-body text-xs italic text-muted-foreground hover:text-primary"
          onClick={onAddExit}
          data-testid="add-exit-button"
        >
          ⊕ dig or link an exit…
        </button>
      </Panel>

      <Panel label="Ownership">
        <Kv term="Deed">not tracked yet</Kv>
        <Kv term="Tenants">not tracked yet</Kv>
        <Kv term="Listing">{room.is_public ? 'public' : 'private'}</Kv>
      </Panel>

      <Panel label="People" count={room.functionaries.length}>
        <p className="font-body text-sm text-muted-foreground">
          {room.functionaries.length > 0 ? room.functionaries.join(', ') : 'none posted'}
        </p>
      </Panel>

      <Panel label="Ambience" count={room.ambient_counts.lines + room.ambient_counts.emits}>
        <Kv term="Entry lines">{room.ambient_counts.lines}</Kv>
        <Kv term="Linger emits">{room.ambient_counts.emits}</Kv>
        <Kv term="Comfort">
          level {comfort.level} ({comfort.points >= 0 ? '+' : ''}
          {comfort.points})
        </Kv>
      </Panel>

      <Panel label="Places & Things" count={room.places.length}>
        <Kv term="Places">{placeNames}</Kv>
        <Kv term="Feature slot">{featureLabel}</Kv>
      </Panel>

      <Panel label="Law & Danger">
        {dangerStats.length > 0 ? (
          dangerStats.map((stat) => (
            <Kv key={stat.key} term={stat.label}>
              {stat.effective}
            </Kv>
          ))
        ) : (
          <p className="font-body text-sm text-muted-foreground">not tracked yet</p>
        )}
      </Panel>

      <Panel label="Secrets & Story" count={cluesCount + clueTriggersCount}>
        <Kv term="Clues">{cluesCount}</Kv>
        <Kv term="Clue triggers">{clueTriggersCount}</Kv>
      </Panel>

      <Panel label="Art">
        {room.art_url ? (
          <img
            src={room.art_url}
            alt={`Art for ${room.name}`}
            className="max-h-24 w-full border object-cover"
            data-testid="marginalia-art"
          />
        ) : (
          <p className="font-body text-sm text-muted-foreground">bare walls</p>
        )}
        <button
          type="button"
          className="mt-1 text-left font-body text-xs italic text-muted-foreground hover:text-primary"
          onClick={onOpenArt}
          data-testid="open-art-button"
        >
          ✎ hang art…
        </button>
      </Panel>

      <Panel label="Resonance">
        {resonanceStat ? (
          <Kv term={resonanceStat.label}>{resonanceStat.effective}</Kv>
        ) : (
          <p className="font-body text-sm text-muted-foreground">unresonant ground</p>
        )}
      </Panel>
    </aside>
  );
}
