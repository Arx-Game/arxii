import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { addSessionMessage, resetGame, setSessionConnectionStatus } from '@/store/gameSlice';
import { setAccount } from '@/store/authSlice';
import { parseGameMessage } from './parseGameMessage';
import { GAME_MESSAGE_TYPE, WS_MESSAGE_TYPE } from './types';
import { emitActionResult } from './actionResultBus';
import { emitHazardPrompt } from './hazardPromptBus';

import type {
  ActionResultPayload,
  CommandErrorPayload,
  GameMessage,
  HazardPromptPayload,
  IncomingMessage,
  InteractionWsPayload,
  KudosReceivedPayload,
  MailArrivedPayload,
  OutgoingMessage,
  RoomStatePayload,
  ScenePayload,
  SocketMessageType,
} from './types';
import type { CommandSpec } from '@/game/types';
import { handleRoomStatePayload } from './handleRoomStatePayload';
import { handleScenePayload } from './handleScenePayload';
import { handleCommandPayload } from './handleCommandPayload';
import { handleInteractionPayload } from './handleInteractionPayload';
import { handleRoulettePayload } from './handleRoulettePayload';
import type { RoulettePayload } from '@/components/roulette/types';
import { handleBattleStatePayload } from './handleBattleStatePayload';
import type { BattleStatePayload } from '@/battles/types';
import { handleKudosReceivedPayload } from './handleKudosReceivedPayload';
import { handleMailArrivedPayload } from './handleMailArrivedPayload';

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { NavigateFunction } from 'react-router-dom';
import type { MyRosterEntry } from '@/roster/types';
import type { AppDispatch } from '@/store/store';
import { getWebSocketUrl } from '@/config';
import { toast } from 'sonner';
import { fetchAccount } from '@/evennia_replacements/api';
import { queryClient } from '@/queryClient';

const sockets: Record<string, WebSocket> = {};
// Names with a connect() in flight (pre-socket-creation await window) — the
// synchronous guard that prevents two near-simultaneous connects from each
// opening a socket and leaking the first (2026-07 audit).
const connecting = new Set<string>();
// Per-character reconnect bookkeeping (2026-07 audit): an abnormal close used
// to just mark the session disconnected and stop — a network blip silently
// froze the feed until the user manually re-clicked their character tab.
const reconnectAttempts: Record<string, number> = {};
const reconnectTimers: Record<string, ReturnType<typeof setTimeout>> = {};
const MAX_RECONNECT_ATTEMPTS = 6;

/** Swallow reconnect failures so a transient socket error doesn't reject the timer. */
const swallowReconnectError = (): void => {};

function clearReconnect(character: string) {
  reconnectAttempts[character] = 0;
  const timer = reconnectTimers[character];
  if (timer !== undefined) {
    clearTimeout(timer);
    delete reconnectTimers[character];
  }
}

/** A plain system message shown when a frame is malformed or unrecognized. */
function buildSystemFallbackMessage(content: string): GameMessage {
  return { content, timestamp: Date.now(), type: GAME_MESSAGE_TYPE.SYSTEM };
}

/** Narrows a parsed frame to the `[type, args, kwargs?]` wire shape. */
function isIncomingMessage(value: unknown): value is IncomingMessage {
  return Array.isArray(value) && value.length >= 2;
}

interface IncomingMessageContext {
  character: MyRosterEntry['name'];
  args: unknown[];
  kwargs: Record<string, unknown> | undefined;
  dispatch: AppDispatch;
  navigate: NavigateFunction;
}

type IncomingMessageHandler = (ctx: IncomingMessageContext) => void;

// One entry per control message type the server can push; anything absent
// from this table falls through to parseGameMessage as a regular game
// message. Keeping this as a lookup table (rather than an if-chain) is what
// keeps the socket message listener's cognitive complexity in check.
const INCOMING_MESSAGE_HANDLERS: Partial<Record<SocketMessageType, IncomingMessageHandler>> = {
  [WS_MESSAGE_TYPE.ROOM_STATE]: ({ character, kwargs, dispatch }) =>
    handleRoomStatePayload(character, kwargs as unknown as RoomStatePayload, dispatch),

  [WS_MESSAGE_TYPE.SCENE]: ({ character, kwargs, dispatch }) =>
    handleScenePayload(character, kwargs as unknown as ScenePayload, dispatch),

  [WS_MESSAGE_TYPE.COMMAND_ERROR]: ({ kwargs }) => {
    const { error, command } = (kwargs as unknown as CommandErrorPayload) ?? {};
    toast.error(error, { description: command });
  },

  [WS_MESSAGE_TYPE.KUDOS_RECEIVED]: ({ kwargs }) =>
    handleKudosReceivedPayload(kwargs as unknown as KudosReceivedPayload | undefined),

  // Defensive: kwargs may be undefined if the server sends a malformed frame.
  // emitActionResult is a side-effecting bus call only - every listener is
  // responsible for its own toast/UX.
  [WS_MESSAGE_TYPE.ACTION_RESULT]: ({ kwargs }) =>
    emitActionResult(
      (kwargs as unknown as ActionResultPayload) ?? { success: false, message: null, data: null }
    ),

  [WS_MESSAGE_TYPE.ROULETTE_RESULT]: ({ kwargs, dispatch }) =>
    handleRoulettePayload(kwargs as unknown as RoulettePayload, dispatch),

  [WS_MESSAGE_TYPE.BATTLE_STATE]: ({ kwargs }) =>
    handleBattleStatePayload(kwargs as unknown as BattleStatePayload),

  [WS_MESSAGE_TYPE.MAIL_ARRIVED]: ({ kwargs }) =>
    handleMailArrivedPayload(kwargs as unknown as MailArrivedPayload),

  [WS_MESSAGE_TYPE.HAZARD_PROMPT]: ({ kwargs }) =>
    emitHazardPrompt(kwargs as unknown as HazardPromptPayload),

  [WS_MESSAGE_TYPE.INTERACTION]: ({ character, kwargs, dispatch, navigate }) =>
    handleInteractionPayload(
      character,
      kwargs as unknown as InteractionWsPayload,
      dispatch,
      navigate
    ),

  [WS_MESSAGE_TYPE.COMMANDS]: ({ character, args }) =>
    handleCommandPayload(character, args as CommandSpec[]),

  // Broadcast to every account session on each successful puppet - nothing to
  // do client-side (the open handler already re-puppets), but without this
  // entry the frame fell through to parseGameMessage and rendered as raw
  // JSON noise in the system lane (2026-07 audit).
  [WS_MESSAGE_TYPE.PUPPET_CHANGED]: () => {
    return undefined;
  },
};

/** Routes one parsed incoming websocket frame to its handler, or renders it as a plain game message. */
function dispatchIncomingMessage(
  character: MyRosterEntry['name'],
  parsed: IncomingMessage,
  dispatch: AppDispatch,
  navigate: NavigateFunction
): void {
  const [msgType, args, kwargs] = parsed;
  // msgType arrives off the wire, so look it up as an own property only. A crafted
  // type ("constructor", "toString", "__proto__") would otherwise resolve to an
  // inherited Object.prototype member and get invoked as if it were a handler.
  const handler = Object.prototype.hasOwnProperty.call(INCOMING_MESSAGE_HANDLERS, msgType)
    ? INCOMING_MESSAGE_HANDLERS[msgType]
    : undefined;
  if (typeof handler === 'function') {
    handler({ character, args, kwargs, dispatch, navigate });
    return;
  }

  // Regular game message
  const message = parseGameMessage(parsed);
  dispatch(addSessionMessage({ character, message }));
}

export function useGameSocket() {
  const dispatch = useAppDispatch();
  const account = useAppSelector((state) => state.auth.account);
  const navigate = useNavigate();

  const disconnectAll = useCallback(() => {
    // Explicit disconnect: cancel any pending reconnects first so a closing
    // socket doesn't immediately resurrect itself.
    Object.keys(reconnectTimers).forEach(clearReconnect);
    Object.values(sockets).forEach((socket) => socket.close());
  }, []);

  const connect = useCallback(
    async (character: MyRosterEntry['name']) => {
      if (sockets[character] || connecting.has(character)) return;
      connecting.add(character);

      let currentAccount = account;
      if (!currentAccount) {
        try {
          currentAccount = await fetchAccount();
          if (currentAccount) {
            dispatch(setAccount(currentAccount));
          } else {
            connecting.delete(character);
            navigate('/login');
            return;
          }
        } catch {
          connecting.delete(character);
          navigate('/login');
          return;
        }
      }

      // Clean websocket URL - middleware will inject session auth from cookies
      const url = getWebSocketUrl(window.location);
      const socket = new WebSocket(url);
      sockets[character] = socket;
      connecting.delete(character);

      socket.addEventListener('open', () => {
        clearReconnect(character);
        dispatch(setSessionConnectionStatus({ character, status: true }));
        const puppet: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [`@ic ${character}`], {}];
        socket.send(JSON.stringify(puppet));
        // Backfill anything that arrived while no socket was listening: the
        // REST feed is the source of record and may still be "fresh" for up
        // to staleTime, so force it stale on every (re)connect.
        queryClient.invalidateQueries({ queryKey: ['scene-interactions'] }).catch(() => {});
      });

      socket.addEventListener('close', (event) => {
        dispatch(setSessionConnectionStatus({ character, status: false }));
        delete sockets[character];
        if (event.code === 1000) {
          clearReconnect(character);
          // Only reset game state if this was the last active connection
          const remainingConnections = Object.keys(sockets).length;
          if (remainingConnections === 0) {
            dispatch(resetGame());
          }
          return;
        }
        // Abnormal close: reconnect with capped exponential backoff
        // (1s, 2s, 4s, ... 30s). The open handler re-puppets and backfills.
        const attempt = (reconnectAttempts[character] ?? 0) + 1;
        if (attempt > MAX_RECONNECT_ATTEMPTS) return;
        reconnectAttempts[character] = attempt;
        const delay = Math.min(1000 * 2 ** (attempt - 1), 30_000);
        reconnectTimers[character] = setTimeout(() => {
          delete reconnectTimers[character];
          connect(character).catch(swallowReconnectError);
        }, delay);
      });

      socket.addEventListener('message', (event) => {
        let parsed: unknown;

        try {
          parsed = JSON.parse(event.data);
        } catch {
          // Bad JSON frame: surface as a system message and bail.
          dispatch(
            addSessionMessage({
              character,
              message: buildSystemFallbackMessage(String(event.data)),
            })
          );
          return;
        }

        if (!isIncomingMessage(parsed)) {
          // Unexpected structure: stringify and show
          dispatch(
            addSessionMessage({
              character,
              message: buildSystemFallbackMessage(JSON.stringify(parsed)),
            })
          );
          return;
        }

        dispatchIncomingMessage(character, parsed, dispatch, navigate);
      });
    },
    [account, dispatch, navigate]
  );

  const send = useCallback((character: MyRosterEntry['name'], command: string) => {
    const socket = sockets[character];
    if (socket && socket.readyState === WebSocket.OPEN) {
      const message: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [command], {}];
      socket.send(JSON.stringify(message));
    }
  }, []);

  /**
   * Invoke a registered backend action over the websocket.
   *
   * The action dispatcher resolves `action` against the registry, runs the
   * backing service, and emits an `ACTION_RESULT` message. Listeners that
   * care about the outcome should subscribe via `useActionResult`.
   *
   * Silently no-ops when the named character has no open socket — callers
   * should disable buttons until the session is connected, but a missing
   * socket should not blow up the page.
   */
  const executeAction = useCallback(
    (character: MyRosterEntry['name'], action: string, kwargs: Record<string, unknown> = {}) => {
      const socket = sockets[character];
      if (socket && socket.readyState === WebSocket.OPEN) {
        const message: OutgoingMessage = [WS_MESSAGE_TYPE.EXECUTE_ACTION, [], { action, kwargs }];
        socket.send(JSON.stringify(message));
      }
    },
    []
  );

  return { connect, send, disconnectAll, executeAction };
}
