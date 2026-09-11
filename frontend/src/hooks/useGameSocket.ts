import { useAppDispatch, useAppSelector } from '@/store/hooks';
import {
  addSessionMessage,
  addSessionDiagnostic,
  addAmbientNotice,
  resetGame,
  setSessionConnectionStatus,
  setSessionLifecycle,
} from '@/store/gameSlice';
import { setAccount } from '@/store/authSlice';
import { parseGameMessage } from './parseGameMessage';
import { WS_MESSAGE_TYPE } from './types';
import { emitActionResult } from './actionResultBus';
import { emitHazardPrompt } from './hazardPromptBus';

import type {
  ActionResultPayload,
  CommandErrorPayload,
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
import { reconcileStoredDrafts } from '@/game/useDraftStore';
import { fetchPoseSubmission } from '@/scenes/queries';

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
// Per-character monotonic connection generation (#3760): incremented on every
// connection attempt, including automatic reconnects. Each connection's message
// handler closes over the generation it was created with, so a message that
// arrives after that connection has been superseded (a newer generation now
// current) can be dropped before it reaches any state update - reconnects are
// frequent in production (#3745), and a stale message flipping readiness or
// clearing an in-flight draft is exactly what this guards against.
const connectionGenerations: Record<string, number> = {};

function nextGeneration(character: string): number {
  const next = (connectionGenerations[character] ?? 0) + 1;
  connectionGenerations[character] = next;
  return next;
}

/**
 * Exported ONLY for use in beforeEach in test files. Do not call in production
 * code. Clears every module-level record this file keeps (`sockets`,
 * `connecting`, `reconnectAttempts`, `connectionGenerations`) and cancels any
 * pending reconnect timers before clearing `reconnectTimers` itself — a
 * leftover `setTimeout` from a prior test's abnormal-close path would
 * otherwise fire mid-way through a later, unrelated test.
 */
export function __resetGameSocketModuleStateForTests(): void {
  Object.keys(sockets).forEach((character) => delete sockets[character]);
  connecting.clear();
  Object.keys(reconnectAttempts).forEach((character) => delete reconnectAttempts[character]);
  Object.values(reconnectTimers).forEach((timer) => clearTimeout(timer));
  Object.keys(reconnectTimers).forEach((character) => delete reconnectTimers[character]);
  Object.keys(connectionGenerations).forEach(
    (character) => delete connectionGenerations[character]
  );
}

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

type IncomingMessageHandler = (ctx: IncomingMessageContext) => boolean | void;

// One case per control message type the server can push; anything not matched
// here falls through to parseGameMessage as a regular game message. A switch on
// the literal type constants keeps this dispatch's cognitive complexity in check
// the way the old if-chain did not, while keeping the chosen handler a matter of
// explicit control flow. An object/Map lookup keyed by the wire-supplied type
// reads the same but makes the call target a value derived from user input,
// which is exactly what CodeQL js/unvalidated-dynamic-method-call flags.
function handlerFor(msgType: SocketMessageType): IncomingMessageHandler | undefined {
  switch (msgType) {
    case WS_MESSAGE_TYPE.ROOM_STATE:
      return ({ character, kwargs, dispatch }) =>
        handleRoomStatePayload(character, kwargs as unknown as RoomStatePayload, dispatch);

    case WS_MESSAGE_TYPE.SCENE:
      return ({ character, kwargs, dispatch }) =>
        handleScenePayload(character, kwargs as unknown as ScenePayload, dispatch);

    case WS_MESSAGE_TYPE.COMMAND_ERROR:
      return ({ kwargs }) => {
        const { error, command } = (kwargs as unknown as CommandErrorPayload) ?? {};
        toast.error(error, { description: command });
      };

    case WS_MESSAGE_TYPE.KUDOS_RECEIVED:
      return ({ kwargs }) =>
        handleKudosReceivedPayload(kwargs as unknown as KudosReceivedPayload | undefined);

    // Defensive: kwargs may be undefined if the server sends a malformed frame.
    // emitActionResult is a side-effecting bus call only - every listener is
    // responsible for its own toast/UX.
    case WS_MESSAGE_TYPE.ACTION_RESULT:
      return ({ kwargs }) =>
        emitActionResult(
          (kwargs as unknown as ActionResultPayload) ?? {
            success: false,
            message: null,
            data: null,
          }
        );

    case WS_MESSAGE_TYPE.ROULETTE_RESULT:
      return ({ kwargs, dispatch }) =>
        handleRoulettePayload(kwargs as unknown as RoulettePayload, dispatch);

    case WS_MESSAGE_TYPE.BATTLE_STATE:
      return ({ kwargs }) => handleBattleStatePayload(kwargs as unknown as BattleStatePayload);

    case WS_MESSAGE_TYPE.MAIL_ARRIVED:
      return ({ kwargs }) => handleMailArrivedPayload(kwargs as unknown as MailArrivedPayload);

    case WS_MESSAGE_TYPE.HAZARD_PROMPT:
      return ({ kwargs }) => emitHazardPrompt(kwargs as unknown as HazardPromptPayload);

    case WS_MESSAGE_TYPE.INTERACTION:
      return ({ character, kwargs, dispatch, navigate }) =>
        handleInteractionPayload(
          character,
          kwargs as unknown as InteractionWsPayload,
          dispatch,
          navigate
        );

    case WS_MESSAGE_TYPE.COMMANDS:
      return ({ character, args }) => handleCommandPayload(character, args as CommandSpec[]);

    // Broadcast to every account session on each successful puppet - nothing to
    // do client-side (the open handler already re-puppets), but without this
    // case the frame fell through to parseGameMessage and rendered as raw
    // JSON noise in the system lane (2026-07 audit).
    case WS_MESSAGE_TYPE.PUPPET_CHANGED:
      return () => undefined;

    default:
      return undefined;
  }
}
/** Routes one parsed incoming websocket frame to its handler, or renders it as a plain game message. */
function dispatchIncomingMessage(
  character: MyRosterEntry['name'],
  parsed: IncomingMessage,
  dispatch: AppDispatch,
  navigate: NavigateFunction
): void {
  const [msgType, args, kwargs] = parsed;
  const handler = handlerFor(msgType);
  if (handler) {
    const accepted = handler({ character, args, kwargs, dispatch, navigate });
    // Lifecycle is socket-owned so protocol handlers remain small and usable
    // in isolation. A room_state frame is the only readiness confirmation.
    if (msgType === WS_MESSAGE_TYPE.ROOM_STATE && accepted !== false) {
      const roomPayload = kwargs as { scene?: unknown } | undefined;
      dispatch(
        setSessionLifecycle({
          character,
          lifecycleState: roomPayload?.scene ? 'ready-scene' : 'ready-no-scene',
        })
      );
    } else if (msgType === WS_MESSAGE_TYPE.SCENE) {
      // Ending a confirmed scene is a presentation transition, not a
      // readiness claim. Start/update frames wait for room_state confirmation.
      const scenePayload = kwargs as { action?: unknown } | undefined;
      if (scenePayload?.action === 'end') {
        dispatch(setSessionLifecycle({ character, lifecycleState: 'aftermath' }));
      }
    }
    return;
  }

  // Only legacy text-like frames may enter the compact notice lane. Control
  // frames must never fall through as JSON or appear as authored prose.
  if (
    msgType === WS_MESSAGE_TYPE.TEXT ||
    msgType === WS_MESSAGE_TYPE.LOGGED_IN ||
    msgType === WS_MESSAGE_TYPE.VN_MESSAGE ||
    msgType === WS_MESSAGE_TYPE.MESSAGE_REACTION
  ) {
    const message = parseGameMessage(parsed);
    const metadata = kwargs as Record<string, unknown> | undefined;
    if (
      msgType === WS_MESSAGE_TYPE.TEXT &&
      (metadata?.type === 'narrative' || metadata?.type === 'gemit')
    ) {
      dispatch(
        addAmbientNotice({
          character,
          message: message.content,
          timestamp: typeof metadata?.timestamp === 'string' ? metadata.timestamp : undefined,
        })
      );
    } else {
      dispatch(addSessionMessage({ character, message }));
    }
    return;
  }
  dispatch(
    addSessionDiagnostic({
      character,
      message: 'A connection message was not recognized. Try again.',
    })
  );
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
      dispatch(setSessionLifecycle({ character, lifecycleState: 'entering' }));
      const generation = nextGeneration(character);

      let currentAccount = account;
      if (!currentAccount) {
        try {
          currentAccount = await fetchAccount();
          if (currentAccount) {
            dispatch(setAccount(currentAccount));
          } else {
            connecting.delete(character);
            dispatch(setSessionLifecycle({ character, lifecycleState: 'entry-error' }));
            navigate('/login');
            return;
          }
        } catch {
          connecting.delete(character);
          dispatch(setSessionLifecycle({ character, lifecycleState: 'entry-error' }));
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
        dispatch(setSessionLifecycle({ character, lifecycleState: 'entering' }));

        // Step 1: reauthorize. Re-puppet immediately — everything downstream
        // (room state, the ability to send) depends on this landing first.
        // `setSessionConnectionStatus` (connected=true) is intentionally NOT
        // dispatched here — see Step 3 below, which fires it only after
        // reconciliation, not on the raw socket 'open' event.
        const puppet: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [`@ic ${character}`], {}];
        socket.send(JSON.stringify(puppet));

        // Step 2: reconcile (#3760 Task 12). A reconnect means any send
        // dispatched on the now-superseded connection may never have gotten
        // its ACTION_RESULT - the connection that would have delivered it is
        // gone, and a fresh connection's message handler runs under a new
        // generation that will never receive a frame addressed to the old
        // one (see the message listener's generation-discard check below).
        // So before this connection is allowed to declare the session ready,
        // resolve every stranded pending/unknown draft's fate against the
        // Task 6 lookup endpoint - the only reconciliation channel reachable
        // from here (this handler is module-scope, outside React, so it has
        // no live `beginSend()` to resend through; see `reconcileStoredDrafts`'s
        // doc comment in useDraftStore.ts for the full reasoning).
        reconcileStoredDrafts(fetchPoseSubmission)
          .catch(() => {
            // A rejected lookup already left its own stored draft untouched
            // (see reconcileStoredDrafts) - nothing further to do here.
          })
          .finally(() => {
            // Step 3: only now flip ready / invalidate - but only if this
            // connection is still the current one. Reconciliation is async;
            // a newer reconnect may have already superseded this generation
            // while the lookup(s) were in flight, in which case this
            // connection's belated "ready" must be discarded exactly like
            // the message listener discards a belated frame.
            if (generation !== connectionGenerations[character]) return;
            dispatch(setSessionConnectionStatus({ character, status: true }));
            // Backfill anything that arrived while no socket was listening:
            // the REST feed is the source of record and may still be
            // "fresh" for up to staleTime, so force it stale on every
            // (re)connect.
            queryClient.invalidateQueries({ queryKey: ['scene-interactions'] }).catch(() => {});
          });
      });

      socket.addEventListener('close', (event) => {
        // A reconnect can replace this socket before its close event arrives.
        // Never let stale frames or stale closes mutate the current session.
        if (sockets[character] !== socket) return;
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
        dispatch(
          setSessionLifecycle({
            character,
            lifecycleState: attempt > MAX_RECONNECT_ATTEMPTS ? 'entry-error' : 'reconnecting',
          })
        );
        if (attempt > MAX_RECONNECT_ATTEMPTS) return;
        reconnectAttempts[character] = attempt;
        const delay = Math.min(1000 * 2 ** (attempt - 1), 30_000);
        reconnectTimers[character] = setTimeout(() => {
          delete reconnectTimers[character];
          connect(character).catch(swallowReconnectError);
        }, delay);
      });

      socket.addEventListener('message', (event) => {
        // Discard before any state update: this connection may have already
        // been superseded by a newer one (e.g. a reconnect fired) by the time
        // this frame arrives. The generation check catches this earliest (it
        // advances the instant a new connect() starts, before that attempt's
        // socket even exists); the socket-identity check is a second,
        // independent guard against a stale frame from an old socket object.
        if (generation !== connectionGenerations[character]) return;
        if (sockets[character] !== socket) return;

        let parsed: unknown;

        try {
          parsed = JSON.parse(event.data);
        } catch {
          // Bad JSON is a diagnostic, not story content.
          dispatch(
            addSessionDiagnostic({
              character,
              message: 'A connection message was invalid. Try again.',
            })
          );
          return;
        }

        if (!isIncomingMessage(parsed)) {
          // Unexpected structure is a diagnostic, not story content.
          dispatch(
            addSessionDiagnostic({
              character,
              message: 'A connection message had an unexpected format.',
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

  /** Current connection generation for `character` (0 if never connected). */
  const currentGeneration = useCallback(
    (character: MyRosterEntry['name']) => connectionGenerations[character] ?? 0,
    []
  );

  return { connect, send, disconnectAll, executeAction, currentGeneration };
}
