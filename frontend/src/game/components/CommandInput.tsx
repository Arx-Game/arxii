import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useActionResult } from '@/hooks/actionResultBus';
import type { ActionResultPayload } from '@/hooks/types';
import { useDraftStore } from '@/game/useDraftStore';
import type { DraftKey, DraftMode } from '@/game/useDraftStore';
import { dbrefToId } from '@/lib/dbref';
import { RichTextInput } from '@/components/RichTextInput';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { ModeSelector } from '@/scenes/components/ModeSelector';
import { LanguageSelector } from './LanguageSelector';
import { CompanionSelector } from './CompanionSelector';
import { companionEmote } from '@/companions/api';
import type { CompanionSummary } from '@/companions/types';
import { ActionAttachment } from '@/scenes/components/ActionAttachment';
import {
  EntranceTechniqueAttachment,
  type EntranceTechniqueSelection,
} from '@/scenes/components/EntranceTechniqueAttachment';
import type { TargetCandidate } from '@/scenes/components/TargetPicker';
import { useAppSelector } from '@/store/hooks';
import type { MyRosterEntry } from '@/roster/types';
import type { Interaction } from '@/scenes/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import { createActionRequest } from '@/scenes/actionQueries';
import { submitPose, fetchScene, sceneKeys, fetchPoseSubmission } from '@/scenes/queries';
import type { SceneDetail } from '@/scenes/queries';

export interface ComposerMode {
  command: string; // "pose" | "say" | "tt" | "whisper"
  targets: string[]; // persona names for @targeting
  label: string; // "Pose -> The Grand Ballroom"
  /** #2165: audience is fixed by the active conversation tab — mode switching disabled. */
  locked?: boolean;
}

// #3069 — `page` is a real OOC telnet command (CmdPage,
// commands/evennia_overrides/communication.py); it has no telnet alias
// (no `tell`), so it's the only addition here. Without it, `page
// <name>=<message>` typed while a composer mode is set (pose/say/etc.) gets
// wrapped by buildFullCommand into IC prose instead of reaching CmdPage
// verbatim as OOC.
const KNOWN_COMMANDS: ReadonlySet<string> = new Set([
  'pose',
  'say',
  'emit',
  'emote',
  'whisper',
  'tt',
  'tabletalk',
  'page',
]);

// #2993 — the language selector only makes sense for speech modes (comprehension
// gating applies to say/whisper/mutter; pose/emit/tt carry no in-fiction language).
const SPEECH_COMPOSER_MODES = new Set(['say', 'whisper', 'mutter']);
const MAX_POSE_LENGTH = 10_000;

// #3760 Task 10 — composer modes dispatched via `executeAction` (structured
// ack + idempotency) instead of raw WS text. `tt` (tabletalk) dispatches
// through the same registry action as `pose` (key `"pose"`), scoped to the
// `currentPlaceId` prop -- when it's unresolved (not currently at a place,
// or the places query hasn't loaded yet) tt falls back to the legacy
// `send()` path rather than risk broadcasting room-wide.
const EXECUTE_ACTION_SPEECH_MODES = new Set(['say', 'whisper', 'tt']);

/**
 * Builds the full command string for a trimmed input given the active composer
 * mode. When the input already starts with an explicit known command, or there
 * is no composer mode, the input is sent verbatim.
 */
function buildFullCommand(trimmed: string, composerMode?: ComposerMode): string {
  if (!composerMode) return trimmed;

  const firstWord = trimmed.split(' ')[0].toLowerCase();
  const hasExplicitCommand = KNOWN_COMMANDS.has(firstWord);
  if (hasExplicitCommand) return trimmed;

  if (composerMode.command === 'whisper' && composerMode.targets.length > 0) {
    return `whisper ${composerMode.targets[0]}=${trimmed}`;
  }
  const targetStr = composerMode.targets.length > 0 ? ` @${composerMode.targets.join(',@')} ` : ' ';
  return `${composerMode.command}${targetStr}${trimmed}`;
}

interface CommandInputProps {
  character: MyRosterEntry['name'];
  composerMode?: ComposerMode;
  onModeChange?: (mode: ComposerMode) => void;
  targetToAppend?: string | null;
  onTargetConsumed?: () => void;
  sceneId?: string;
  actionAttachment?: ActionAttachmentInfo | null;
  onActionAttach?: (action: ActionAttachmentInfo) => void;
  onActionDetach?: () => void;
  onSubmitAction?: (action: ActionAttachmentInfo) => void;
  /** Persona id for the active character — used to call submit_pose REST endpoint. */
  personaId?: number | null;
  /** IDs of the persona's unlinked ACTION interactions in this scene (from usePendingUnlinkedActions). */
  pendingActionIds?: number[];
  /** IDs the user has explicitly detached — these will be omitted from action_link_ids. */
  detachedActionIds?: number[];
  /** Called after a successful pose submit so the parent can clear detachedActionIds. */
  onPoseSubmitted?: () => void;
  /**
   * Whether the viewer's active persona is currently present at a Place in
   * this scene (#2156) — gates the `tt` (tabletalk) mode in `ModeSelector`.
   * Derived by the composition root (`GamePage`/`SceneDetailPage`) from the
   * shared `['scene-places', id]` query so it dedupes with `PlaceBar`'s own
   * fetch. Defaults to `false` when omitted.
   */
  isAtPlace?: boolean;
  /**
   * The Place the viewer's active persona is currently present at, if any
   * (#3760 Task 10 fix) — the `pk` `tt` dispatches via `executeAction` as
   * the registry `pose` action's `place` kwarg. Same derivation/dedupe as
   * `isAtPlace` (from `GamePage`/`SceneDetailPage`'s shared
   * `['scene-places', id]` query); `null`/omitted falls back to the legacy
   * `send()` path for tt.
   */
  currentPlaceId?: number | null;
  /**
   * The "speaking as" identity chip (#2166 Decision 3) — the character whose
   * voice this composer speaks in. Rendered at the START of `leftSlot`,
   * before `ModeSelector`, whenever provided; absent for legacy callers that
   * haven't been threaded yet. Mis-attributed poses are the multi-character
   * equivalent of the wrong-scene-pose bug, so this is always-on (not gated
   * behind having more than one character) once the caller supplies it.
   */
  speakingAs?: { name: string; thumbnailUrl: string | null };
  /** Narrative play uses Cmd/Ctrl+Enter; legacy command drawers may retain Enter. */
  submitOnEnter?: boolean;
  /** Account/context-scoped draft key. Drafts remain per-tab and never contain received text. */
  draftScope?: string;
  replyTarget?: Interaction | null;
  onCancelReply?: () => void;
  ready?: boolean;
}

export function CommandInput({
  character,
  composerMode,
  onModeChange,
  targetToAppend,
  onTargetConsumed,
  sceneId,
  actionAttachment,
  onActionAttach,
  onActionDetach,
  onSubmitAction,
  personaId,
  pendingActionIds,
  detachedActionIds,
  onPoseSubmitted,
  isAtPlace,
  currentPlaceId,
  speakingAs,
  submitOnEnter = true,
  draftScope,
  replyTarget,
  onCancelReply,
  ready = true,
}: CommandInputProps) {
  const draftStorageKey = draftScope ? `arx:play-draft:v1:${draftScope}` : null;
  const [command, setCommand] = useState(() => {
    if (!draftStorageKey) return '';
    try {
      return sessionStorage.getItem(draftStorageKey) ?? '';
    } catch {
      return '';
    }
  });
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const previousDraftKey = useRef(draftStorageKey);
  const skipPersistOnce = useRef(false);
  const suppressDraftFlush = useRef(false);
  useEffect(() => {
    if (previousDraftKey.current === draftStorageKey) return;
    previousDraftKey.current = draftStorageKey;
    skipPersistOnce.current = true;
    try {
      setCommand(draftStorageKey ? (sessionStorage.getItem(draftStorageKey) ?? '') : '');
    } catch {
      setCommand('');
    }
  }, [draftStorageKey]);
  useEffect(() => {
    if (skipPersistOnce.current) {
      skipPersistOnce.current = false;
      return;
    }
    if (!draftStorageKey) return;
    const timer = window.setTimeout(() => {
      try {
        if (command) sessionStorage.setItem(draftStorageKey, command);
        else sessionStorage.removeItem(draftStorageKey);
      } catch {
        /* Storage can be unavailable; the in-memory draft remains usable. */
      }
    }, 500);
    return () => {
      window.clearTimeout(timer);
      // A reference view can temporarily unmount the composer. Flush the
      // current draft so opening history immediately cannot lose text.
      if (suppressDraftFlush.current) {
        suppressDraftFlush.current = false;
        return;
      }
      try {
        if (draftStorageKey && command) sessionStorage.setItem(draftStorageKey, command);
      } catch {
        /* keep the in-memory draft when storage is unavailable */
      }
    };
  }, [command, draftStorageKey]);
  // #904 — next pose is a Make-an-Entrance (pose_kind=entry, REST path only).
  const [isEntrance, setIsEntrance] = useState(false);
  // #3294 — pose as this bonded, present companion instead of yourself. Sticky
  // (not one-shot like isEntrance) until the player clears it back to "Speak
  // as yourself" — puppeting a companion is usually more than one line.
  const [asCompanion, setAsCompanion] = useState<CompanionSummary | null>(null);
  // #2183 — optional technique+target attached to the next entrance pose.
  const [entranceTechnique, setEntranceTechnique] = useState<EntranceTechniqueSelection | null>(
    null
  );
  const submittingRef = useRef(false);
  const { send, executeAction } = useGameSocket();

  const activeCharacter = useAppSelector((state) => state.game.active);
  const roomCharacters = useAppSelector((state) => {
    if (!activeCharacter) return [];
    const room = state.game.sessions[activeCharacter]?.room;
    return room?.characters ?? [];
  });
  // Optional chained even though `RootState.auth` isn't nullable in the real
  // store: several existing tests mock `@/store/hooks` with a partial state
  // that omits `auth` entirely, and this must not throw for them.
  const accountId = useAppSelector((state) => state.auth?.account?.id) ?? 0;

  // #3760 Task 10 — say/whisper draft acknowledgement (Task 8's
  // `useDraftStore`). Keyed by `draftScope` (falling back to a
  // per-character default), the same scope the legacy `command`/
  // sessionStorage-v1 draft below already uses — mode-switching within one
  // conversation tab already shares one textarea/draft today, so sharing one
  // `useDraftStore` slot across say/whisper modes on the same tab is not a
  // new behavior.
  const draftKey = useMemo<DraftKey>(
    () => ({
      accountId,
      personaId: personaId ?? 0,
      conversationKey: draftScope ?? `character:${character}`,
    }),
    [accountId, personaId, draftScope, character]
  );
  const draftStore = useDraftStore(draftKey);
  const { draft } = draftStore;
  // Mirrors `command` without forcing `handleActionResult` (below) to
  // resubscribe to the action-result bus on every keystroke.
  const commandRef = useRef(command);
  useEffect(() => {
    commandRef.current = command;
  }, [command]);
  // The most recently dispatched say/whisper send awaiting its ACTION_RESULT.
  // `ActionResultPayload` carries no client_request_id (see
  // `hooks/types.ts`), so correlation is best-effort: the next action_result
  // event on the bus is assumed to be this dispatch's response, the same
  // assumption every other `useActionResult` consumer in this codebase
  // already makes (WardrobePage, StatusPanel, ...). A fast concurrent
  // dispatch from elsewhere in the app could in principle misattribute —
  // see the Task 10 report.
  const pendingSpeechRef = useRef<{ clientRequestId: string; text: string } | null>(null);

  const { data: sceneDetail } = useQuery<SceneDetail>({
    queryKey: sceneKeys.detail(sceneId ?? ''),
    queryFn: () => fetchScene(sceneId!),
    enabled: !!sceneId,
  });

  const clearStoredDraft = useCallback(() => {
    suppressDraftFlush.current = true;
    if (!draftStorageKey) return;
    try {
      sessionStorage.removeItem(draftStorageKey);
    } catch {
      /* keep in memory */
    }
  }, [draftStorageKey]);

  // #3760 Task 11 — a `pending`/`unknown` draft hydrated from storage with
  // NO live send in flight means the tab was reopened (or navigated back to)
  // mid-flight, not that a send is actively in progress right now.
  // Recomputed every render rather than latched in state: `pendingSpeechRef`
  // is set synchronously by `handleSubmit` (below) in the same tick as the
  // `beginSend()` call that flips `draft.status` to `pending`, so a genuine
  // live send's very first "pending" render already has a matching ref and
  // never reads as stranded; discarding or resuming naturally clears this
  // too, since both take `draft.status` out of pending/unknown.
  const isStrandedDraft =
    (draft.status === 'pending' || draft.status === 'unknown') &&
    pendingSpeechRef.current?.clientRequestId !== draft.clientRequestId;
  // "Unsent draft from <context>" (demo Screen 4) — the closest available
  // stand-in for a room/place name is the active composer mode's own label
  // (e.g. "Pose → The Gilded Hart"), falling back to the draft scope or bare
  // character name for legacy callers that don't supply one.
  const strandedContext = composerMode?.label ?? draftScope ?? character;

  // #3760 Task 11 review fix — exactly ONE delivery-state banner renders at a
  // time. The demo's Screen 3b ("unknown, still actively failed") and Screen
  // 4 ("stranded, reopened tab") are ALTERNATIVES, not simultaneous states:
  // a reloaded `unknown`-status draft is by definition stranded (see
  // `isStrandedDraft` above), so it gets the stranded banner's
  // Discard/"Resume & retry" pair, never the live-unknown banner's "Check
  // status"/Retry pair layered on top of it too. `checkingSubmissionStatus`
  // deliberately doesn't participate here (it's a transient loading flag on
  // the `unknown` banner itself, not a banner-selection input).
  let composerBanner: 'stranded' | 'pending' | 'rejected' | 'unknown' | null = null;
  if (isStrandedDraft) {
    composerBanner = 'stranded';
  } else if (draft.status === 'pending') {
    composerBanner = 'pending';
  } else if (draft.status === 'rejected' && draft.rejectionReason) {
    composerBanner = 'rejected';
  } else if (draft.status === 'unknown') {
    composerBanner = 'unknown';
  }

  // #3760 Task 11 — "Check status" against the Task 6 writer-only lookup
  // endpoint. `enabled: false`: never fetched automatically, only via the
  // button's explicit `refetch()` (the established `enabled: false` +
  // manual-trigger pattern in this codebase, e.g. `stories/queries.ts`'s
  // `useSessionRequest`).
  const { refetch: checkSubmissionStatus, isFetching: checkingSubmissionStatus } = useQuery({
    queryKey: ['pose-submission', draft.clientRequestId ?? ''],
    queryFn: () => {
      const clientRequestId = draft.clientRequestId;
      return clientRequestId ? fetchPoseSubmission(clientRequestId) : Promise.resolve(null);
    },
    enabled: false,
  });

  const handleCheckStatus = useCallback(() => {
    const clientRequestId = draft.clientRequestId;
    if (!clientRequestId) return;
    checkSubmissionStatus().then((result) => {
      if (result.data) {
        // Found: the send landed after all. Same ack-gated clearing as a
        // live ACTION_RESULT success (only clears `command` when it still
        // matches the content that was actually sent).
        draftStore.acknowledge(clientRequestId);
        if (commandRef.current === draft.content) {
          setCommand('');
          clearStoredDraft();
        }
      } else if (!result.error) {
        toast.error('No record of that send — safe to retry.');
      } else {
        toast.error(
          result.error instanceof Error ? result.error.message : 'Failed to check status.'
        );
      }
    });
  }, [draft.clientRequestId, draft.content, checkSubmissionStatus, draftStore, clearStoredDraft]);

  const handleDiscardStrandedDraft = useCallback(() => {
    draftStore.discard();
    setCommand('');
    clearStoredDraft();
  }, [draftStore, clearStoredDraft]);

  // #3760 Task 10 — resolves the say/whisper dispatch tracked in
  // `pendingSpeechRef`: acknowledge/clear on success, reject + toast on
  // failure. Ack-gated clearing (mirrors the REST `submitPose` path just
  // below: the draft is only cleared on success — a rejected/failed send
  // must not silently eat the player's text). Guards against clobbering a
  // newer, unsent edit the same way `useDraftStore.acknowledge` guards its
  // own state: only clears `command` when it still matches the text that was
  // actually sent.
  const handleActionResult = useCallback(
    (payload: ActionResultPayload) => {
      const pending = pendingSpeechRef.current;
      if (!pending) return;
      pendingSpeechRef.current = null;
      if (payload.success) {
        draftStore.acknowledge(pending.clientRequestId);
        if (commandRef.current === pending.text) {
          setHistory((prev) => [...prev, pending.text]);
          setHistoryIndex(-1);
          setCommand('');
          clearStoredDraft();
        }
      } else {
        draftStore.reject(pending.clientRequestId, payload.message ?? 'Failed to send.');
        toast.error(payload.message ?? 'Failed to send.');
      }
    },
    [draftStore, clearStoredDraft]
  );
  useActionResult(handleActionResult);

  // #3760 Task 12 — a reconnect can happen while a say/whisper send is
  // genuinely in flight on THIS tab (`pendingSpeechRef` still set, its
  // ACTION_RESULT still outstanding). The websocket connection that would
  // have delivered that ACTION_RESULT is gone once it drops; a fresh
  // connection's message handler runs under a new connection generation
  // (#3760 Task 9) and will never receive a frame addressed to the old one,
  // so waiting for `handleActionResult` to eventually resolve this send
  // would wait forever. `useGameSocket`'s reconnect-open handler (#3760 Task
  // 12) only flips the session's `isConnected` flag - and so only lets
  // `ready` go back to true - AFTER it has reauthorized AND reconciled
  // every STORED draft; a `false -> true` transition here (never the
  // initial mount, since `wasReadyRef` seeds from the first render's own
  // `ready` value) is therefore a genuine reconnect completing. A send this
  // tab is still tracking through `pendingSpeechRef` is exactly the case
  // that storage-level reconciliation cannot see (nothing persists "a send
  // is live in this exact tab right now"), so it is handled here instead:
  // flip the draft to `unknown` (this is `markUnknown()`'s first production
  // call site) and immediately try the same lookup the "Check status"
  // button uses, rather than leaving the composer stuck showing "Sending…"
  // for a reply that will never arrive.
  const wasReadyRef = useRef(ready);
  useEffect(() => {
    const wasReady = wasReadyRef.current;
    wasReadyRef.current = ready;
    if (wasReady || !ready) return;
    const pending = pendingSpeechRef.current;
    if (!pending) return;
    pendingSpeechRef.current = null;
    draftStore.markUnknown(pending.clientRequestId);
    handleCheckStatus();
  }, [ready, draftStore, handleCheckStatus]);

  const handleSubmit = useCallback(() => {
    if (!ready || submittingRef.current) return;
    const trimmed = command.trim();
    if (!trimmed) return;
    if (command.length > MAX_POSE_LENGTH) {
      toast.error(`Your pose is too long. Maximum ${MAX_POSE_LENGTH.toLocaleString()} characters.`);
      return;
    }

    // #3760 Task 10 — say/whisper/tt candidate mode from the LIVE composer
    // selection right now. Only relevant when the active mode itself is
    // say/whisper/tt AND the player didn't type an explicit different
    // command inline (KNOWN_COMMANDS override stays on the legacy `send()`
    // path unchanged — that's free-text, not a structured dispatch).
    const firstWord = trimmed.split(' ')[0].toLowerCase();
    const hasExplicitCommandOverride = KNOWN_COMMANDS.has(firstWord);
    const liveSpeechMode: DraftMode | null =
      !hasExplicitCommandOverride &&
      composerMode &&
      EXECUTE_ACTION_SPEECH_MODES.has(composerMode.command)
        ? { command: composerMode.command, targets: composerMode.targets }
        : null;
    // #3760 Task 11 critical fix — an untouched `pending`/`rejected`/`unknown`
    // draft (nothing has gone through `setContent` since the original
    // attempt, which is what `draft.status !== 'clean'` implies here — see
    // `beginSend`'s doc comment for the precise, ref-based version of this
    // same check) MUST dispatch under the mode it was ORIGINALLY composed in,
    // never whatever mode happens to be live right now — a stranded whisper
    // reopened on the room tab, or a mode switch mid-session without editing
    // the text, must not silently redispatch as a public say/pose. This is
    // the SAME rule `beginSend()` applies for `clientRequestId` reuse,
    // applied here so the caller can decide WHICH dispatch branch to take
    // before calling it (a plain Send, Retry, and "Resume & retry" — every
    // path that can reach `handleSubmit` — all resolve through this one spot,
    // never a live `composerMode` prop read separately at dispatch time).
    const resolvedSpeechMode: DraftMode | null =
      draft.status !== 'clean' && draft.mode ? draft.mode : liveSpeechMode;
    // The mode actually driving this send: prefer the resolved speech mode
    // (say/whisper/tt, live or preserved); fall back to the live composerMode
    // for a genuine pose/explicit-override send, where there is no stored
    // override to defend against.
    const dispatchMode = resolvedSpeechMode ?? composerMode;

    // I4: Whisper mode requires a target — don't send a malformed command.
    // Checked against the RESOLVED mode, not the live composerMode prop, for
    // the same reason as above.
    if (resolvedSpeechMode?.command === 'whisper' && resolvedSpeechMode.targets.length === 0) {
      return;
    }

    submittingRef.current = true;

    // #3294 — companion-attributed pose: a dedicated dispatch, bypassing
    // ModeSelector's mode entirely (a companion emote is always a room-level
    // pose). The server re-validates ownership + room presence on every call
    // (CompanionPresentPrerequisite), so a stale toggle (companion left the
    // room mid-composition) fails loud via toast rather than ghost-posing.
    if (asCompanion) {
      companionEmote(asCompanion.id, trimmed)
        .then(() => {
          setHistory((prev) => [...prev, trimmed]);
          setHistoryIndex(-1);
          setCommand('');
          clearStoredDraft();
        })
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : 'Failed to emote as companion.';
          toast.error(message);
        })
        .finally(() => {
          submittingRef.current = false;
        });
      return;
    }

    // #3760 Task 11 critical fix — `buildFullCommand`'s legacy-WS fallback
    // (used by the whisper/tt branches below when their dispatch precondition
    // fails, and by the plain-pose path) must build against `dispatchMode`,
    // never the live `composerMode` prop directly: a stored whisper/tt
    // override whose target/place can't be resolved right now still has to
    // fall through AS THE ORIGINAL MODE (e.g. `whisper <name>=...`), not as
    // whatever the live ModeSelector currently shows.
    const fullCommand = buildFullCommand(
      trimmed,
      dispatchMode
        ? { command: dispatchMode.command, targets: dispatchMode.targets, label: '' }
        : undefined
    );

    if (actionAttachment && onSubmitAction) {
      onSubmitAction(actionAttachment);
    }

    // #3760 Task 10 — say/whisper dispatch via `executeAction` (structured
    // ack + idempotency), replacing the raw WS text-command send for these
    // two modes. `tt` is deliberately excluded from `executeAction` itself
    // (it rides the `pose` registry action below) — see
    // EXECUTE_ACTION_SPEECH_MODES's comment. `resolvedSpeechMode` (not a live
    // composerMode read) decides which branch fires, per the critical-fix
    // comment above `resolvedSpeechMode`'s own declaration.
    if (resolvedSpeechMode && resolvedSpeechMode.command === 'say') {
      const clientRequestId = draftStore.beginSend(liveSpeechMode);
      pendingSpeechRef.current = { clientRequestId, text: trimmed };
      executeAction(character, 'say', { text: trimmed, client_request_id: clientRequestId });
      submittingRef.current = false;
      return;
    }

    if (resolvedSpeechMode && resolvedSpeechMode.command === 'whisper') {
      // The wire's generic ObjectDB resolution (`_resolve_registry_kwargs`,
      // `server/conf/inputfuncs.py`) only resolves `<field>_id` int kwargs —
      // it cannot resolve a target by name. `resolvedSpeechMode.targets`
      // only ever carries persona display names (see `ComposerMode.targets`
      // doc comment), so the name is resolved against `roomCharacters`
      // (which carries a `dbref`, unlike `sceneDetail.participants`) to a
      // `target_id`. When it can't be resolved (target not in this room's
      // character list — e.g. a scene participant who has since left),
      // fall through to the legacy `send()` path below rather than crash or
      // silently drop the whisper.
      const whisperTargetName = resolvedSpeechMode.targets[0];
      const whisperTargetChar = roomCharacters.find((c) => c.name === whisperTargetName);
      const whisperTargetId = whisperTargetChar ? dbrefToId(whisperTargetChar.dbref) : 0;
      if (whisperTargetId > 0) {
        const clientRequestId = draftStore.beginSend(liveSpeechMode);
        pendingSpeechRef.current = { clientRequestId, text: trimmed };
        executeAction(character, 'whisper', {
          text: trimmed,
          target_id: whisperTargetId,
          client_request_id: clientRequestId,
        });
        submittingRef.current = false;
        return;
      }
    }

    if (resolvedSpeechMode && resolvedSpeechMode.command === 'tt') {
      // tt (tabletalk) rides the `pose` registry action, scoped to the
      // viewer's current Place via the `place` kwarg (PoseAction.execute(),
      // `src/actions/definitions/communication.py` — resolves an int pk
      // itself and verifies real PlacePresence, mirroring the established
      // `_resolve_room()` REST/WS-dispatch pattern). `currentPlaceId` comes
      // from the composition root's places query (`GamePage`/
      // `SceneDetailPage`); when it's not resolved (not currently at a
      // place, or the query hasn't loaded), fall through to the legacy
      // `send()` path below rather than risk a room-wide broadcast.
      if (currentPlaceId != null) {
        const clientRequestId = draftStore.beginSend(liveSpeechMode);
        pendingSpeechRef.current = { clientRequestId, text: trimmed };
        executeAction(character, 'pose', {
          text: trimmed,
          place: currentPlaceId,
          client_request_id: clientRequestId,
        });
        submittingRef.current = false;
        return;
      }
    }

    // Determine submission path. The REST path (submit_pose) is now the
    // canonical route for scene poses: it carries scene_id explicitly and the
    // server enforces the co-location check (actor must be in the scene's
    // room) that the WebSocket command protocol can't express. WS remains
    // for non-pose commands (say, whisper, tt, ...) and for poses outside a
    // scene (no sceneId/personaId — e.g. room-only poses with no active scene).
    // Gated on `dispatchMode` (not live `composerMode`) for the same reason
    // as `fullCommand` above — a stored whisper/tt override that fell
    // through the branches above (target/place unresolvable) must never be
    // treated as a pose and REST-submitted to the whole room.
    const isPose = !dispatchMode || dispatchMode.command === 'pose';
    const detachedSet = new Set(detachedActionIds ?? []);
    const hasDetachments = detachedSet.size > 0;
    const usesRestSubmit = isPose && sceneId !== undefined && personaId != null;

    if (usesRestSubmit) {
      // REST path: explicit action_link_ids override when the user has detached
      // one or more pending actions. WebSocket send() is intentionally skipped
      // to avoid creating two POSE Interactions for the same pose. The draft
      // is only cleared on success (#2156 review fix) — a rejected request
      // (e.g. the co-location 400) must not silently eat the player's text;
      // the composer keeps it and the server's error surfaces via toast so a
      // retry doesn't mean retyping the whole pose.
      const composerTargets = composerMode?.targets ?? [];
      submitPose({
        persona_id: personaId,
        scene_id: Number(sceneId),
        content: trimmed,
        pose_kind: isEntrance ? 'entry' : undefined,
        ...(composerTargets.length > 0 ? { target_names: composerTargets } : {}),
        ...(hasDetachments
          ? {
              action_link_ids: (pendingActionIds ?? []).filter((id) => !detachedSet.has(id)),
            }
          : {}),
      })
        .then((response) => {
          onPoseSubmitted?.();
          setHistory((prev) => [...prev, trimmed]);
          setHistoryIndex(-1);
          setCommand('');
          clearStoredDraft();
          setIsEntrance(false);
          // #2183 — an entrance technique was attached: dispatch it now that
          // the entry pose exists, so EntranceAction can anchor to it. Plain
          // entrances (no technique attached) send nothing further — byte
          // identical to pre-#2183 behavior.
          if (isEntrance && entranceTechnique && sceneId !== undefined) {
            createActionRequest(sceneId, {
              action_key: 'entrance',
              technique_id: entranceTechnique.techniqueId,
              target_persona_id: entranceTechnique.targetPersonaId,
              entry_interaction_id: typeof response?.id === 'number' ? response.id : undefined,
            }).catch((error: unknown) => {
              const message =
                error instanceof Error ? error.message : 'Failed to dispatch entrance technique.';
              toast.error(message);
            });
          }
          setEntranceTechnique(null);
        })
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : 'Failed to submit pose.';
          toast.error(message);
        })
        .finally(() => {
          submittingRef.current = false;
        });
      return;
    }

    // WebSocket path: existing behavior. Server-side auto-link will attach
    // any pending ACTION interactions when the POSE is created.
    send(character, fullCommand);

    setHistory((prev) => [...prev, trimmed]);
    setHistoryIndex(-1);
    setCommand('');
    clearStoredDraft();
    // I3: Clear synchronously — React batches the state updates above,
    // so this runs on the same tick and prevents double-submission.
    submittingRef.current = false;
  }, [
    character,
    command,
    composerMode,
    draft.status,
    draft.mode,
    send,
    executeAction,
    draftStore,
    roomCharacters,
    currentPlaceId,
    actionAttachment,
    onSubmitAction,
    sceneId,
    personaId,
    pendingActionIds,
    asCompanion,
    detachedActionIds,
    onPoseSubmitted,
    isEntrance,
    entranceTechnique,
    clearStoredDraft,
    ready,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'ArrowUp' && command === '') {
      e.preventDefault();
      if (history.length > 0) {
        const newIndex = historyIndex <= 0 ? history.length - 1 : historyIndex - 1;
        setHistoryIndex(newIndex);
        setCommand(history[newIndex]);
      }
    }
  };

  const handleToggleEntrance = useCallback(() => {
    const next = !isEntrance;
    setIsEntrance(next);
    if (!next) {
      // Turning the toggle off drops any attached entrance technique too —
      // it's meaningless without an entrance pose to anchor it to.
      setEntranceTechnique(null);
    }
  }, [isEntrance]);

  const handleModeChange = useCallback(
    (mode: string) => {
      if (!onModeChange || !composerMode || composerMode.locked) return;
      const label = mode.charAt(0).toUpperCase() + mode.slice(1);
      onModeChange({
        command: mode,
        targets: composerMode.targets,
        label,
      });
    },
    [onModeChange, composerMode]
  );

  const handleChange = useCallback(
    (val: string) => {
      setCommand(val);
      setHistoryIndex(-1);
      // Keeps `draftStore.draft.content` in sync with what's on screen so
      // `beginSend()` (called at submit time, a later render) can correctly
      // tell "same content as last send" (reuse the id — protects against a
      // double-Enter double-dispatch) from "new content" (mint a fresh id).
      // `beginSend()`'s own doc comment warns against calling `setContent`
      // and `beginSend` back to back in one synchronous handler — this is
      // why the sync lives here, in the change handler, one render ahead of
      // any submit, rather than inline in `handleSubmit`.
      draftStore.setContent(val);
    },
    [draftStore]
  );

  const ghostText = useMemo(() => {
    // #3294 \u2014 a companion emote overrides the normal mode ghost text entirely
    // (submission bypasses composerMode while active).
    if (asCompanion) {
      return `\ud83d\udc3e As ${asCompanion.name}`;
    }
    if (!composerMode) return '';
    const mode = composerMode.command.charAt(0).toUpperCase() + composerMode.command.slice(1);
    let text: string;
    if (composerMode.targets.length > 0) {
      text = `${mode} \u2192 ${composerMode.targets.join(', ')}`;
    } else {
      text = composerMode.label || mode;
    }
    if (actionAttachment) {
      text += ` | \u2694 ${actionAttachment.name}`;
      if (actionAttachment.target) text += ` \u2192 ${actionAttachment.target}`;
    }
    if (isEntrance) {
      text += ' | \u2728 Entrance';
    }
    return text;
  }, [asCompanion, composerMode, actionAttachment, isEntrance]);

  // #2183 — entrance-technique target candidates: the scene's participants.
  const entranceCandidates = useMemo<TargetCandidate[]>(
    () => (sceneDetail?.participants ?? []).map((p) => ({ id: p.id, name: p.name })),
    [sceneDetail?.participants]
  );

  const autocompleteItems = useMemo(() => {
    if (sceneId && sceneDetail?.participants) {
      return sceneDetail.participants.map((p) => ({
        name: p.name,
        thumbnail_url: null as string | null,
      }));
    }
    return roomCharacters;
  }, [sceneId, sceneDetail?.participants, roomCharacters]);

  // Append @name when a pending target arrives
  useEffect(() => {
    if (targetToAppend) {
      setCommand((prev) => {
        const prefix = prev.trim() ? prev + ' ' : '';
        return `${prefix}@${targetToAppend}`;
      });
      onTargetConsumed?.();
    }
  }, [targetToAppend, onTargetConsumed]);

  return (
    <div className="play-composer-safe shrink-0 border-t">
      {draftStore.storageUnavailable && (
        <div
          className="flex items-center gap-2 bg-muted/60 px-3 py-1.5 text-xs text-muted-foreground"
          data-testid="storage-unavailable-notice"
        >
          <span>Draft kept in this tab only — it won&#39;t survive a reload.</span>
        </div>
      )}
      {composerBanner === 'stranded' && (
        <div
          className="flex flex-wrap items-center gap-2 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-600"
          data-testid="stranded-draft-banner"
        >
          <span className="min-w-0 flex-1">
            <strong>Unsent draft from {strandedContext}.</strong> This never got a response last
            time.
          </span>
          <span className="flex shrink-0 gap-2">
            <button
              type="button"
              className="min-h-8 underline"
              onClick={handleDiscardStrandedDraft}
            >
              Discard
            </button>
            <button type="button" className="min-h-8 underline" onClick={handleSubmit}>
              Resume &amp; retry
            </button>
          </span>
        </div>
      )}
      {composerBanner === 'pending' && (
        <div
          className="flex items-center gap-2 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-600"
          data-testid="send-pending-banner"
        >
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
          <span>Sending…</span>
        </div>
      )}
      {composerBanner === 'rejected' && (
        <div
          className="flex items-center gap-2 bg-destructive/10 px-3 py-1.5 text-xs text-destructive"
          data-testid="send-rejected-banner"
        >
          <span>Not sent — {draft.rejectionReason}</span>
        </div>
      )}
      {composerBanner === 'unknown' && (
        <div
          className="flex flex-wrap items-center gap-2 bg-muted/60 px-3 py-1.5 text-xs text-muted-foreground"
          data-testid="send-unknown-banner"
        >
          <span className="min-w-0 flex-1">
            Connection dropped before we heard back. We don&#39;t know if this sent.
          </span>
          <span className="flex shrink-0 gap-2">
            <button
              type="button"
              className="min-h-8 underline"
              onClick={handleCheckStatus}
              disabled={checkingSubmissionStatus}
            >
              Check status
            </button>
            <button type="button" className="min-h-8 underline" onClick={handleSubmit}>
              Retry
            </button>
          </span>
        </div>
      )}
      {replyTarget && (
        <div
          className="flex items-center gap-2 bg-accent/40 px-3 py-1.5 text-xs"
          data-testid="reply-context"
        >
          <span className="min-w-0 flex-1 truncate">
            Replying to <strong>{replyTarget.persona.name}</strong>:{' '}
            {replyTarget.content.slice(0, 140)}
          </span>
          <button type="button" className="min-h-8 underline" onClick={onCancelReply}>
            Cancel reply
          </button>
        </div>
      )}
      <RichTextInput
        value={command}
        onChange={handleChange}
        onSubmit={handleSubmit}
        onKeyDown={handleKeyDown}
        rows={5}
        submitOnEnter={submitOnEnter}
        submitDisabled={!ready}
        disabled={draft.status === 'pending'}
        leftSlot={
          <div className="flex items-center gap-1">
            {speakingAs && (
              <span
                className="flex items-center gap-1 rounded-full bg-accent/50 py-0.5 pl-0.5 pr-2 text-xs font-medium"
                title={`Speaking as ${speakingAs.name}`}
                data-testid="speaking-as-chip"
              >
                <PersonaAvatar
                  source={{ name: speakingAs.name, thumbnailUrl: speakingAs.thumbnailUrl }}
                  size="sm"
                />
                <span>{speakingAs.name}</span>
              </span>
            )}
            <ModeSelector
              currentMode={composerMode?.command ?? 'pose'}
              onModeChange={handleModeChange}
              isAtPlace={isAtPlace ?? false}
              locked={composerMode?.locked ?? false}
            />
            {composerMode && SPEECH_COMPOSER_MODES.has(composerMode.command) && (
              <LanguageSelector character={character} />
            )}
            <CompanionSelector value={asCompanion} onChange={setAsCompanion} />
          </div>
        }
        rightSlot={
          sceneId ? (
            <div className="flex items-center gap-1">
              {personaId != null && (
                <button
                  type="button"
                  aria-label="Make an entrance"
                  title="Make an entrance: your next pose announces your arrival and others can acclaim it"
                  aria-pressed={isEntrance}
                  onClick={handleToggleEntrance}
                  className={`rounded px-1 text-sm transition-colors ${
                    isEntrance ? 'bg-amber-500/20 text-amber-500' : 'text-muted-foreground'
                  }`}
                >
                  ✨
                </button>
              )}
              {isEntrance && personaId != null && (
                <EntranceTechniqueAttachment
                  personaId={personaId}
                  candidates={entranceCandidates}
                  value={entranceTechnique}
                  onChange={setEntranceTechnique}
                />
              )}
              <ActionAttachment
                sceneId={sceneId}
                attachment={actionAttachment ?? null}
                onAttach={(action) => onActionAttach?.(action)}
                onDetach={() => onActionDetach?.()}
                targetName={composerMode?.targets[0]}
              />
            </div>
          ) : undefined
        }
        ghostText={ghostText}
        autocompleteItems={autocompleteItems}
      />
      {(command.length > MAX_POSE_LENGTH - 500 || command.length > MAX_POSE_LENGTH) && (
        <p
          className={`px-3 py-1 text-xs ${command.length > MAX_POSE_LENGTH ? 'text-destructive' : 'text-muted-foreground'}`}
          role={command.length > MAX_POSE_LENGTH ? 'alert' : undefined}
        >
          {command.length.toLocaleString()} / {MAX_POSE_LENGTH.toLocaleString()} characters
        </p>
      )}
    </div>
  );
}
