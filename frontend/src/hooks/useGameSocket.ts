import { useAppDispatch, useAppSelector } from '@/store/hooks';
import {
  addConsoleLine,
  addFeedNote,
  addSessionMessage,
  addSessionDiagnostic,
  endSession,
  resetGame,
  setSessionConnectionStatus,
  setSessionPuppetConfirmed,
  setSessionLifecycle,
  resetSessionRoomRevision,
  setRoomStateResyncStatus,
} from '@/store/gameSlice';
import { setAccount } from '@/store/authSlice';
import { parseGameMessage } from './parseGameMessage';
import { WS_MESSAGE_TYPE, EVENNIA_CONTROL_TYPES } from './types';
import { classifyText } from '@/game/feedKinds';
import { emitActionResult } from './actionResultBus';
import { emitHazardPrompt } from './hazardPromptBus';
import { recordUnknownFrame } from './unknownFrames';

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

type PendingResync = {
  character: MyRosterEntry['name'];
  generation: number;
  requestId: string;
  timer: ReturnType<typeof setTimeout>;
  snapshotAccepted: boolean;
  snapshotRevision?: { epoch: string; sequence: number };
};
const pendingResync = new Map<string, PendingResync>();

function finishResync(
  pending: PendingResync,
  dispatch: AppDispatch,
  status: 'success' | 'partial' | 'failure',
  error?: string
): void {
  if (pendingResync.get(pending.requestId) !== pending) return;
  clearTimeout(pending.timer);
  pendingResync.delete(pending.requestId);
  dispatch(
    setRoomStateResyncStatus({ character: pending.character, status, ...(error ? { error } : {}) })
  );
}

function markResyncSnapshot(
  character: MyRosterEntry['name'],
  generation: number,
  requestId: string,
  kwargs: Record<string, unknown>,
  dispatch: AppDispatch
): void {
  const pending = pendingResync.get(requestId);
  if (!pending || pending.character !== character || pending.generation !== generation) return;
  pending.snapshotAccepted = true;
  if (typeof kwargs.state_epoch === 'string' && Number.isInteger(kwargs.state_sequence)) {
    pending.snapshotRevision = {
      epoch: kwargs.state_epoch,
      sequence: kwargs.state_sequence as number,
    };
  }
  // Keep pending until the acknowledgement arrives; the timeout/close path
  // reports partial success when only the snapshot made it through.
  dispatch(setRoomStateResyncStatus({ character, status: 'pending' }));
}

function finishGenerationResyncs(
  character: MyRosterEntry['name'],
  generation: number,
  dispatch: AppDispatch
): void {
  for (const pending of pendingResync.values()) {
    if (pending.character !== character || pending.generation !== generation) continue;
    finishResync(
      pending,
      dispatch,
      pending.snapshotAccepted ? 'partial' : 'failure',
      pending.snapshotAccepted
        ? 'Room state refreshed, but confirmation was lost.'
        : 'Room state refresh failed. Retry.'
    );
  }
}

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
  pendingResync.forEach((pending) => clearTimeout(pending.timer));
  pendingResync.clear();
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
    case WS_MESSAGE_TYPE.STATE_RESYNC:
      return ({ character, kwargs, dispatch }) => {
        if (
          typeof kwargs?.client_request_id !== 'string' ||
          typeof kwargs.state_epoch !== 'string' ||
          !Number.isInteger(kwargs.state_sequence) ||
          typeof kwargs.room_id !== 'number' ||
          !Number.isInteger(kwargs.room_id) ||
          (kwargs.scene_id !== null &&
            (typeof kwargs.scene_id !== 'number' || !Number.isInteger(kwargs.scene_id)))
        ) {
          return false;
        }
        const pending = pendingResync.get(kwargs.client_request_id);
        if (
          !pending ||
          pending.character !== character ||
          !pending.snapshotAccepted ||
          !pending.snapshotRevision ||
          pending.snapshotRevision.epoch !== kwargs.state_epoch ||
          pending.snapshotRevision.sequence !== kwargs.state_sequence
        )
          return false;
        const invalidations: Promise<unknown>[] = [];
        if (kwargs.scene_id !== null) {
          invalidations.push(
            queryClient.invalidateQueries({
              queryKey: ['scene-interactions', String(kwargs.scene_id), character],
              exact: true,
            })
          );
          invalidations.push(
            queryClient.invalidateQueries({
              queryKey: ['scene-places', String(kwargs.room_id), character],
              exact: true,
            })
          );
        }
        Promise.all(invalidations).then(
          () => finishResync(pending, dispatch, 'success'),
          () =>
            finishResync(
              pending,
              dispatch,
              'partial',
              'Room state refreshed, but scene data could not be refreshed.'
            )
        );
        return true;
      };

    case WS_MESSAGE_TYPE.STATE_RESYNC_ERROR:
      return ({ character, kwargs, dispatch }) => {
        if (typeof kwargs?.client_request_id !== 'string' || typeof kwargs.code !== 'string') {
          return false;
        }
        const pending = pendingResync.get(kwargs.client_request_id);
        if (!pending || pending.character !== character) return false;
        finishResync(pending, dispatch, 'failure', 'Room state refresh failed. Retry.');
        return true;
      };

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

    // Broadcast to every account session on each successful puppet (#3933).
    // The frame carries a `session_id`, but a socket does not know its own, so
    // the match is on `character_name` alone. What that proves is narrower than
    // "my request landed": SOME session of this account now puppets this
    // socket's character. In the common single-tab case that is this socket's
    // own open-time request; with two tabs on the same character, the sibling's
    // puppet confirms this one too. A per-session confirmation needs the server
    // to echo a request id back on the frame, which #3934's connection-recorder
    // work adds. A puppet_changed for another character (a sibling tab on a
    // different character) is never this socket's confirmation and is ignored.
    case WS_MESSAGE_TYPE.PUPPET_CHANGED:
      return ({ character, kwargs, dispatch }) => {
        if (kwargs?.character_name === character) {
          dispatch(setSessionPuppetConfirmed({ character }));
        }
      };

    // The death condolence line (#3933): toast it, the way command_error's
    // refusal is already toasted.
    case WS_MESSAGE_TYPE.CHARACTER_DIED:
      return ({ kwargs }) => {
        if (typeof kwargs?.body === 'string') toast(kwargs.body);
      };

    // The REST view owns the estate settlement surface; nothing to do here (#3933).
    case WS_MESSAGE_TYPE.ESTATE_SETTLEMENT_OPENED:
      return () => undefined;

    // Evennia's own out-of-band echo; no Arx meaning (#3933).
    case WS_MESSAGE_TYPE.OOB:
      return () => undefined;

    // Evennia's client-settings frame; no Arx meaning (#3933).
    case WS_MESSAGE_TYPE.WEBCLIENT_OPTIONS:
      return () => undefined;

    default:
      return undefined;
  }
}
/** Applies lifecycle transitions associated with handled protocol frames. */
function updateLifecycle(
  character: MyRosterEntry['name'],
  msgType: SocketMessageType,
  kwargs: Record<string, unknown> | undefined,
  accepted: boolean | void,
  dispatch: AppDispatch
): void {
  if (msgType === WS_MESSAGE_TYPE.ROOM_STATE && accepted !== false) {
    const roomPayload = kwargs as { scene?: unknown } | undefined;
    dispatch(
      setSessionLifecycle({
        character,
        lifecycleState: roomPayload?.scene ? 'ready-scene' : 'ready-no-scene',
      })
    );
    return;
  }
  if (msgType !== WS_MESSAGE_TYPE.SCENE) return;
  const scenePayload = kwargs as { action?: unknown } | undefined;
  if (scenePayload?.action === 'end') {
    dispatch(setSessionLifecycle({ character, lifecycleState: 'aftermath' }));
  }
}

const LEGACY_TEXT_TYPES = new Set<SocketMessageType>([
  WS_MESSAGE_TYPE.TEXT,
  WS_MESSAGE_TYPE.LOGGED_IN,
  WS_MESSAGE_TYPE.VN_MESSAGE,
  WS_MESSAGE_TYPE.MESSAGE_REACTION,
]);

/**
 * Renders legacy text-like frames. A `text` frame becomes a feed note (#3856),
 * its kind read from `kwargs.type` (the dict of Evennia's tuple form, which is
 * how commands, movement announcements and the narrative service type their
 * lines); the readers render notes at their timestamp among the interactions.
 * The other legacy frames (login, VN, reactions) keep the message lane.
 */
function dispatchLegacyText(
  character: MyRosterEntry['name'],
  parsed: IncomingMessage,
  msgType: SocketMessageType,
  kwargs: Record<string, unknown> | undefined,
  dispatch: AppDispatch
): boolean {
  if (!LEGACY_TEXT_TYPES.has(msgType)) return false;
  // A milestone the server marks with the puppet handshake, nothing to
  // render (#3933) - `logged_in` used to land in the message lane below.
  if (msgType === WS_MESSAGE_TYPE.LOGGED_IN) return true;
  const message = parseGameMessage(parsed);
  if (msgType === WS_MESSAGE_TYPE.TEXT) {
    // A frame the server tagged for the staff console (#3857) is the answer
    // to a Commands-mode line; it belongs to the console, never the column.
    if (kwargs?.console === true) {
      dispatch(addConsoleLine({ character, content: message.content }));
      return true;
    }
    // Three tags a `text` frame carries for a compatibility line that has
    // its own render elsewhere, so no note is added for it (#3933):
    // `interaction_echo` (the structured Interaction pushed alongside it is
    // the render), `type: 'lifecycle'` (a login milestone, not story), and
    // `on_entry` (the room panel already shows the entry look).
    if (
      kwargs?.interaction_echo === true ||
      kwargs?.type === 'lifecycle' ||
      kwargs?.on_entry === true
    ) {
      return true;
    }
    const subject = typeof kwargs?.subject === 'string' ? kwargs.subject : undefined;
    dispatch(
      addFeedNote({
        character,
        note: {
          kind: classifyText(kwargs?.type, kwargs?.category),
          content: message.content,
          ...(subject ? { subject } : {}),
          timestamp: new Date().toISOString(),
        },
      })
    );
  } else {
    dispatch(addSessionMessage({ character, message }));
  }
  return true;
}

/** Routes one parsed incoming websocket frame to its handler, or renders it as a plain game message. */
function dispatchIncomingMessage(
  character: MyRosterEntry['name'],
  parsed: IncomingMessage,
  dispatch: AppDispatch,
  navigate: NavigateFunction,
  generation: number
): void {
  const [msgType, args, kwargs] = parsed;
  const handler = handlerFor(msgType);
  if (handler) {
    const accepted = handler({ character, args, kwargs, dispatch, navigate });
    updateLifecycle(character, msgType, kwargs, accepted, dispatch);
    if (accepted === false) {
      dispatch(
        addSessionDiagnostic({
          character,
          message: 'A connection message was malformed or out of sequence. Try again.',
        })
      );
    }
    if (
      msgType === WS_MESSAGE_TYPE.ROOM_STATE &&
      accepted !== false &&
      typeof kwargs?.resync_request_id === 'string'
    ) {
      markResyncSnapshot(
        character,
        generation,
        kwargs.resync_request_id,
        kwargs as Record<string, unknown>,
        dispatch
      );
    }
    return;
  }
  if (dispatchLegacyText(character, parsed, msgType, kwargs, dispatch)) return;
  // An Evennia protocol frame (channel, ping, ...) has no Arx meaning and is
  // never story content; anything else is a genuine gap in this client's
  // coverage, recorded for a developer rather than alarmed at a player (#3933).
  if (EVENNIA_CONTROL_TYPES.has(msgType)) return;
  recordUnknownFrame(msgType, generation);
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

  /**
   * Leave the world as one character (#3818): close that character's socket
   * on purpose (a normal close, so the close handler never schedules a
   * reconnect) and forget its session. The server unpuppets when the last
   * session on the character goes, so the character leaves the grid rather
   * than standing there unpiloted. The durable selection is untouched — the
   * player is still playing this character, offscreen; `/game` re-enters.
   */
  const disconnect = useCallback(
    (character: MyRosterEntry['name']) => {
      clearReconnect(character);
      const socket = sockets[character];
      if (socket) socket.close();
      dispatch(endSession(character));
    },
    [dispatch]
  );

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
        // A new socket generation starts a fresh ordering baseline. Stale
        // callbacks from the previous generation are rejected by socket and
        // generation guards before they can reach Redux.
        dispatch(resetSessionRoomRevision({ character }));
        dispatch(setSessionLifecycle({ character, lifecycleState: 'entering' }));

        // Step 1: reauthorize. Puppet immediately — everything downstream
        // (room state, the ability to send) depends on this landing first.
        // Since #3812 the server already puppets the durable selection at
        // login, so for the selected character this is an idempotent no-op;
        // for a socket opening on another character, this is what puppets it
        // here. The reply is `puppet_changed`, not text (#3933) - see
        // `handlerFor`'s PUPPET_CHANGED case, which confirms the handshake.
        // `setSessionConnectionStatus` (connected=true) is intentionally NOT
        // dispatched here — see Step 3 below, which fires it only after
        // reconciliation, not on the raw socket 'open' event.
        const puppet: OutgoingMessage = [WS_MESSAGE_TYPE.PUPPET, [], { character }];
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
        finishGenerationResyncs(character, generation, dispatch);
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

        dispatchIncomingMessage(character, parsed, dispatch, navigate, generation);
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
   * Send a staff Commands-mode line (#3857): the same text frame, flagged so
   * the server tags everything it says back for the console.
   */
  const sendConsole = useCallback(
    (character: MyRosterEntry['name'], command: string) => {
      const socket = sockets[character];
      if (socket && socket.readyState === WebSocket.OPEN) {
        // The console shows the line above what the server says back to it.
        dispatch(addConsoleLine({ character, content: command, sent: true }));
        const message: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [command], { console: true }];
        socket.send(JSON.stringify(message));
      }
    },
    [dispatch]
  );

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

  /** Request a viewer-bound room snapshot without closing this socket. */
  const requestRoomState = useCallback(
    (character: MyRosterEntry['name']): string | null => {
      const existing = Array.from(pendingResync.values()).find(
        (pending) => pending.character === character
      );
      if (existing) return existing.requestId;
      const socket = sockets[character];
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        dispatch(
          setRoomStateResyncStatus({
            character,
            status: 'failure',
            error: 'Room state refresh unavailable while disconnected.',
          })
        );
        return null;
      }
      const requestId = globalThis.crypto.randomUUID();
      const generation = connectionGenerations[character] ?? 0;
      const timer = setTimeout(() => {
        const pending = pendingResync.get(requestId);
        if (!pending || pending.generation !== generation) return;
        finishResync(
          pending,
          dispatch,
          pending.snapshotAccepted ? 'partial' : 'failure',
          pending.snapshotAccepted
            ? 'Room state refreshed, but confirmation was lost.'
            : 'Room state refresh failed. Retry.'
        );
      }, 6000);
      pendingResync.set(requestId, {
        character,
        generation,
        requestId,
        timer,
        snapshotAccepted: false,
      });
      dispatch(setRoomStateResyncStatus({ character, status: 'pending' }));
      const message: OutgoingMessage = [
        WS_MESSAGE_TYPE.REQUEST_ROOM_STATE,
        [],
        { client_request_id: requestId },
      ];
      try {
        socket.send(JSON.stringify(message));
      } catch {
        const pending = pendingResync.get(requestId);
        if (pending)
          finishResync(pending, dispatch, 'failure', 'Room state refresh failed. Retry.');
        return null;
      }
      return requestId;
    },
    [dispatch]
  );

  /** Current connection generation for `character` (0 if never connected). */
  const currentGeneration = useCallback(
    (character: MyRosterEntry['name']) => connectionGenerations[character] ?? 0,
    []
  );

  return {
    connect,
    disconnect,
    send,
    sendConsole,
    disconnectAll,
    executeAction,
    requestRoomState,
    currentGeneration,
  };
}
