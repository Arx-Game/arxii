import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useActionResult } from '@/hooks/actionResultBus';
import type { ActionResultPayload } from '@/hooks/types';
import { useDraftStore } from '@/game/useDraftStore';
import type { DraftKey } from '@/game/useDraftStore';
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
import { submitPose, fetchScene, sceneKeys } from '@/scenes/queries';
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

  const handleSubmit = useCallback(() => {
    if (!ready || submittingRef.current) return;
    const trimmed = command.trim();
    if (!trimmed) return;
    if (command.length > MAX_POSE_LENGTH) {
      toast.error(`Your pose is too long. Maximum ${MAX_POSE_LENGTH.toLocaleString()} characters.`);
      return;
    }

    // I4: Whisper mode requires a target — don't send a malformed command
    if (composerMode?.command === 'whisper' && composerMode.targets.length === 0) {
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

    const fullCommand = buildFullCommand(trimmed, composerMode);

    if (actionAttachment && onSubmitAction) {
      onSubmitAction(actionAttachment);
    }

    // #3760 Task 10 — say/whisper dispatch via `executeAction` (structured
    // ack + idempotency), replacing the raw WS text-command send for these
    // two modes. Only when the active mode itself is say/whisper AND the
    // player didn't type an explicit different command inline (the
    // KNOWN_COMMANDS override buildFullCommand already detects above stays
    // on the legacy `send()` path unchanged — that's free-text, not a
    // structured dispatch). `tt` is deliberately excluded — see
    // EXECUTE_ACTION_SPEECH_MODES's comment.
    const firstWord = trimmed.split(' ')[0].toLowerCase();
    const hasExplicitCommandOverride = KNOWN_COMMANDS.has(firstWord);
    const speechComposerMode: ComposerMode | null =
      !hasExplicitCommandOverride &&
      composerMode &&
      EXECUTE_ACTION_SPEECH_MODES.has(composerMode.command)
        ? composerMode
        : null;

    if (speechComposerMode && speechComposerMode.command === 'say') {
      const clientRequestId = draftStore.beginSend();
      pendingSpeechRef.current = { clientRequestId, text: trimmed };
      executeAction(character, 'say', { text: trimmed, client_request_id: clientRequestId });
      submittingRef.current = false;
      return;
    }

    if (speechComposerMode && speechComposerMode.command === 'whisper') {
      // The wire's generic ObjectDB resolution (`_resolve_registry_kwargs`,
      // `server/conf/inputfuncs.py`) only resolves `<field>_id` int kwargs —
      // it cannot resolve a target by name. `composerMode.targets` only ever
      // carries persona display names (see `ComposerMode.targets` doc
      // comment), so the name is resolved against `roomCharacters` (which
      // carries a `dbref`, unlike `sceneDetail.participants`) to a
      // `target_id`. When it can't be resolved (target not in this room's
      // character list — e.g. a scene participant who has since left),
      // fall through to the legacy `send()` path below rather than crash or
      // silently drop the whisper.
      const whisperTargetName = speechComposerMode.targets[0];
      const whisperTargetChar = roomCharacters.find((c) => c.name === whisperTargetName);
      const whisperTargetId = whisperTargetChar ? dbrefToId(whisperTargetChar.dbref) : 0;
      if (whisperTargetId > 0) {
        const clientRequestId = draftStore.beginSend();
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

    if (speechComposerMode && speechComposerMode.command === 'tt') {
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
        const clientRequestId = draftStore.beginSend();
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
    const isPose = !composerMode || composerMode.command === 'pose';
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
