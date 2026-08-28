import { Link } from 'react-router-dom';
import { ScrollText } from 'lucide-react';

import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setActiveSession, startSession } from '@/store/gameSlice';
import { useSelectCharacterMutation } from '@/roster/queries';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { actingPersonaId } from '@/roster/persona';
import type { MyRosterEntry } from '@/roster/types';
import { WeatherWidget } from '@/weather/components/WeatherWidget';
import { ComfortWidget } from '@/comfort/components/ComfortWidget';
import { sessionAttention } from '@/game/attention';
// #3412 S4 — reused from the Hall (frontend/src/home/hall/queries.ts), not
// duplicated: no import-boundary lint rule exists between home/ and game/
// (checked eslint.config.js — no `boundaries`/`no-restricted-imports` rule
// is configured at all), so the smallest change is importing directly
// rather than relocating the hook.
import { useClockQuery } from '@/home/hall/queries';

import { FormSwitcher } from './FormSwitcher';
import { PersonaSwitcher } from './PersonaSwitcher';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function capitalize(s: string): string {
  return s.length === 0 ? s : s[0].toUpperCase() + s.slice(1);
}

/**
 * Compact IC-season readout (#3412 S4) beside the WeatherWidget. Deliberately
 * NOT hh:mm — WeatherWidget already surfaces `phase + hh:mm` from the same
 * game_clock backend (`get_ic_now`) via its own `ic_time` field, so a second
 * clock readout duplicating that number would just be visual noise (review
 * finding, folded in-branch rather than filed). ClockReadout shows what
 * WeatherWidget lacks — season, plus the paused indicator — and keeps the
 * full date/time/phase in the title tooltip. Mirrors WeatherWidget's own
 * hide-until-resolved shape: renders nothing while loading or on error (no
 * `throwOnError` on `useClockQuery` — an errored fetch just resolves
 * `data: undefined`), so there's no layout jump.
 */
function ClockReadout() {
  const { data: clock } = useClockQuery();
  if (!clock) return null;

  const seasonLabel = capitalize(clock.season);
  const tooltip = [
    `Year ${clock.year}, Month ${clock.month}, Day ${clock.day}, ${pad(clock.hour)}:${pad(clock.minute)}`,
    capitalize(clock.phase),
  ]
    .filter(Boolean)
    .join(' — ');

  return (
    <div
      className="flex items-center gap-1 text-xs text-muted-foreground"
      title={tooltip}
      aria-label="The world clock"
    >
      <span>{seasonLabel}</span>
      {/* PLACEHOLDER copy */}
      {clock.paused && <span className="text-muted-foreground/70">(Paused)</span>}
    </div>
  );
}

interface GameTopBarProps {
  characters: MyRosterEntry[];
}

/**
 * Two-tier attention indicator (#2166 Decision 4a) — direct (unseen
 * whisper/@-target aimed at this character) badges a small red numeric
 * count, mirroring `ConversationTabStrip`'s `UnreadBadge`; ambient (any
 * other unread) shows a muted dot; neither renders nothing.
 */
function AttentionBadge({ direct, ambient }: { direct: number; ambient: boolean }) {
  if (direct > 0) {
    return (
      <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
        {direct}
      </span>
    );
  }
  if (ambient) {
    return (
      <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-muted-foreground/60" />
    );
  }
  return null;
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export function GameTopBar({ characters }: GameTopBarProps) {
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  const { sessions, active } = useAppSelector((state) => state.game);
  const selectCharacter = useSelectCharacterMutation();

  const activeSession = active ? sessions[active] : null;
  const isConnected = activeSession?.isConnected ?? false;

  const handleSelectCharacter = (name: MyRosterEntry['name']) => {
    // #3412 — persist the selection server-side ALONGSIDE the existing
    // puppeting behavior below, never replacing it. Fire-and-forget: the
    // local session switch below is immediate regardless of this call's
    // outcome (see useSelectCharacterMutation's doc comment).
    const entryId = characters.find((c) => c.name === name)?.id;
    if (entryId !== undefined) {
      selectCharacter.mutate(entryId);
    }
    if (sessions[name]) {
      dispatch(setActiveSession(name));
      if (!sessions[name].isConnected) {
        connect(name);
      }
    } else {
      dispatch(startSession(name));
      connect(name);
    }
  };

  const activeCharacter = characters.find((c) => c.name === active);
  const altCharacters = characters.filter((c) => c.name !== active && sessions[c.name]);
  const unplayedCharacters = characters.filter((c) => c.name !== active && !sessions[c.name]);

  return (
    <div className="flex items-center gap-4 border-b bg-card px-4 py-2">
      <span className="text-sm font-bold tracking-wide text-foreground">ARX II</span>

      <div className="mx-2 h-6 w-px bg-border" />

      {characters.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No characters yet -{' '}
          <Link to="/roster" className="text-primary underline">
            browse the roster
          </Link>{' '}
          or{' '}
          <Link to="/characters/create" className="text-primary underline">
            create one
          </Link>
          .
        </p>
      )}

      {active && activeCharacter ? (
        <div className="flex items-center gap-3">
          {/* #3412 — a hydrated-on-reload selection has no live session yet
              (selection isn't presence, so hydration never auto-connects).
              Clickable so there's still a way to (re)connect; harmless
              no-op when already connected (handleSelectCharacter just
              re-activates the existing session). */}
          <button
            onClick={() => handleSelectCharacter(active)}
            title={isConnected ? active : `Connect as ${active}`}
          >
            <Avatar className="h-9 w-9 ring-2 ring-primary">
              <AvatarImage src={activeCharacter.profile_picture_url ?? undefined} alt={active} />
              <AvatarFallback className="text-xs">{getInitials(active)}</AvatarFallback>
            </Avatar>
          </button>
          <PersonaSwitcher
            characterSheetId={activeCharacter.character_id}
            activePersonaId={activeCharacter.active_persona_id}
          />
          <FormSwitcher characterSheetId={activeCharacter.character_id} />
          {/* #3412 S4 — own-sheet link, mode-preserving (new tab so leaving
              the game window doesn't drop the WebSocket session). Route
              param is the RosterEntry id (App.tsx: /characters/:id ->
              CharacterSheetPage reads useParams().id as entryId), not
              character_id. */}
          <Link
            to={`/characters/${activeCharacter.id}`}
            target="_blank"
            rel="noopener"
            className="text-muted-foreground transition-colors hover:text-foreground"
            title="Your character sheet" // PLACEHOLDER copy
            aria-label="Your character sheet" // PLACEHOLDER copy
          >
            <ScrollText className="h-4 w-4" />
          </Link>
        </div>
      ) : null}

      {altCharacters.map((char) => {
        const attention = sessionAttention(sessions[char.name], actingPersonaId(char));
        return (
          <button
            key={char.id}
            onClick={() => handleSelectCharacter(char.name)}
            className="relative opacity-60 transition-opacity hover:opacity-100"
            title={`Switch to ${char.name}`}
          >
            <Avatar className="h-7 w-7">
              <AvatarImage src={char.profile_picture_url ?? undefined} alt={char.name} />
              <AvatarFallback className="text-xs">{getInitials(char.name)}</AvatarFallback>
            </Avatar>
            <AttentionBadge direct={attention.direct} ambient={attention.ambient} />
          </button>
        );
      })}

      {!active &&
        characters.map((char) => (
          <button
            key={char.id}
            onClick={() => handleSelectCharacter(char.name)}
            className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent"
          >
            <Avatar className="h-7 w-7">
              <AvatarImage src={char.profile_picture_url ?? undefined} alt={char.name} />
              <AvatarFallback className="text-xs">{getInitials(char.name)}</AvatarFallback>
            </Avatar>
            <span>{char.name}</span>
          </button>
        ))}

      {active &&
        unplayedCharacters.map((char) => (
          <button
            key={char.id}
            onClick={() => handleSelectCharacter(char.name)}
            className="opacity-40 transition-opacity hover:opacity-80"
            title={`Connect as ${char.name}`}
          >
            <Avatar className="h-6 w-6">
              <AvatarImage src={char.profile_picture_url ?? undefined} alt={char.name} />
              <AvatarFallback className="text-[10px]">{getInitials(char.name)}</AvatarFallback>
            </Avatar>
          </button>
        ))}

      <div className="ml-auto flex items-center gap-3">
        <ComfortWidget characterId={activeCharacter?.character_id ?? null} />
        <ClockReadout />
        <WeatherWidget />
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-xs text-muted-foreground">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>
    </div>
  );
}
