import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import { ExplorationReader } from './ExplorationReader';
import type { GameLifecycleState } from '@/store/gameSlice';
import type { InteractionWsPayload } from '@/hooks/types';
import type { RoomData } from './RoomPanel';
import { ThreadedNarrativeReader } from './ThreadedNarrativeReader';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';
import { ConversationTabStrip, type ConversationTabStripProps } from './ConversationTabStrip';
import { SystemLane } from './SystemLane';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { Interaction } from '@/scenes/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setActiveSession } from '@/store/gameSlice';
import { useSelectCharacterMutation } from '@/roster/queries';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Link } from 'react-router-dom';
import type { MyRosterEntry } from '@/roster/types';
import { characterAttention } from '@/game/attention';
import { AttentionBadge } from '@/game/components/AttentionBadge';
import { loadConversationAnchor, usePlayPreferences } from '../playPreferences';

/** The active scene's live feed, composed once by `GamePage` (#2156). */
export interface GameWindowSceneFeed {
  sceneId: string;
  interactions: Interaction[];
  hasNextPage?: boolean;
  fetchNextPage: () => void;
}

interface GameWindowProps {
  characters: MyRosterEntry[];
  /** When present, the center column renders the threaded scene reader. */
  sceneFeed?: GameWindowSceneFeed;
  /** Structured quiet-room data; absent only while entry is pending. */
  room?: RoomData | null;
  /** Scene-less interaction frames for the exploration reader. */
  ambientInteractions?: InteractionWsPayload[];
  diagnostics?: string[];
  ambientNotices?: string[];
  lifecycleState?: GameLifecycleState;
  composerMode?: ComposerMode;
  onModeChange: (mode: ComposerMode) => void;
  /** The active character's persona id — lifted to GamePage to dedupe the roster query (#2156). */
  personaId: number | null;
  /** Avatar identity-click affordance (#2156) — opens the character-card drawer (Task 7). */
  onAvatarClick?: (persona: PoseUnitAvatarClickPersona) => void;
  /**
   * Scene toolset plumbing (#2156, Task 6) — GamePage is the composition root
   * that owns this state (mirroring `SceneDetailPage`'s handler state); these
   * are threaded straight through to `SceneMessages` and `CommandInput` since
   * both live inside this component.
   */
  onAddTarget?: (personaName: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
  targetToAppend?: string | null;
  onTargetConsumed?: () => void;
  actionAttachment?: ActionAttachmentInfo | null;
  onActionAttach?: (action: ActionAttachmentInfo) => void;
  onActionDetach?: () => void;
  onSubmitAction?: (action: ActionAttachmentInfo) => void;
  pendingActionIds?: number[];
  detachedActionIds?: number[];
  onPoseSubmitted?: () => void;
  /** Explicit parent pose selected by the reader. */
  onReply?: (interaction: Interaction) => void;
  replyTarget?: Interaction | null;
  onCancelReply?: () => void;
  /** Stable account scope for per-tab drafts. */
  draftScopePrefix?: string;
  /**
   * The active character's current physical room id (#3760 Task 14 fix) —
   * `GamePage`'s `roomData?.id`, freshly derived on every `room_state`
   * broadcast (the same value already threaded to `CeremonyRoomCard`,
   * `StoryTray`, and the places query). Folded into the room-anchor
   * conversation's `draftScope` below so a draft typed with no conversation
   * tab open is scoped to the room the player is actually standing in,
   * instead of the constant literal `'room'` — the prior string meant a
   * player's room-anchor draft survived walking through an exit into an
   * entirely different room, which is the opposite of what #3760's spec
   * promises ("my draft in one room to stay put when I travel to
   * another"). `null`/omitted (room state not yet resolved) falls back to
   * the stable literal `'room:unknown'` rather than crashing on a missing
   * id.
   */
  roomId?: number | null;
  /**
   * Human-readable current place name (#3760 demo-fidelity review) — the
   * same value `GamePage` already derives as `sceneData?.name ??
   * roomData?.name ?? 'Room'` for composer-mode labels. Passed through so
   * `CommandInput`'s stranded-draft banner never falls back to the raw
   * `draftScope` cache-key string (`account:1:Name:room:2`) when no
   * composerMode label is set — the default state for a plain room pose.
   */
  roomName?: string;
  /** Whether the viewer's persona is present at a Place in this scene (#2156) — gates `tt`. */
  isAtPlace?: boolean;
  /**
   * The Place the viewer's persona is currently present at, if any (#3760
   * Task 10 fix) — threaded straight to `CommandInput` so `tt` (tabletalk)
   * can dispatch via `executeAction` with a real `place` kwarg, mirroring
   * how say/whisper already do. `null`/omitted when not at a place (or the
   * places query hasn't resolved yet); `tt` falls back to the legacy
   * WebSocket `send()` path in that case.
   */
  currentPlaceId?: number | null;
  /**
   * Human-readable name of the Place `currentPlaceId` refers to, if any
   * (#3787 Screen 3) -- used only for the pre-emptive reply refusal's hint
   * text ("Leave <name> to answer this."), threaded to `ThreadedNarrativeReader`.
   */
  currentPlaceName?: string | null;
  /** `PlaceBar`, rendered directly above the composer (#2156). */
  placeBar?: ReactNode;
  /** `TavernGameWidget`, rendered alongside PlaceBar (#3292). */
  tavernGameWidget?: ReactNode;
  /** `SpeakerQueueBar`, rendered alongside PlaceBar (#2356). */
  speakerQueueBar?: ReactNode;
  /** `PendingActionAttachments`, rendered directly above the composer (#2156). */
  pendingAttachments?: ReactNode;
  /** Open conversation tabs (#2165); absent = no strip, plain feed. */
  conversationTabs?: ConversationTabStripProps;
  /** "Speaking as" identity chip (#2166 Decision 3) — threaded straight to `CommandInput`. */
  speakingAs?: { name: string; thumbnailUrl: string | null };
  /** Read-only historical reference shown in the same reader. */
  reference?: { kind: string; key: string; title: string } | null;
  /**
   * The specific pose id a deep link (a search result or "Recent
   * conversations" row) opened this reference to (#3759 review finding C2)
   * — threaded straight to `ThreadedNarrativeReader`'s own `targetPoseId`
   * prop, which seeds the visible window to include it and scrolls/
   * highlights it once mounted. Absent for a reference opened without a
   * specific pose (a bare conversation browse) and always absent in live mode.
   */
  targetPoseId?: string;
  onReturnToLive?: () => void;
  referenceUnavailable?: boolean;
  referenceLoading?: boolean;
  /** True when the reference fetch failed with a transient/retryable error
   * (i.e. not a 403/404 unavailable-reference) — distinct error UI + a Retry
   * button, alongside the existing Return-to-live affordance. */
  referenceRetryable?: boolean;
  onRetryReference?: () => void;
}

/**
 * Identity of the room-anchor conversation (#3784) — the composer's draft
 * audience when no conversation tab is open. Only ever compared against
 * itself across renders, to tell "the same conversation's key settled" from
 * "a different conversation was selected"; it is never a lookup value.
 */
const ROOM_ANCHOR_CONVERSATION = 'room-anchor';

export function GameWindow({
  characters,
  sceneFeed,
  room,
  ambientInteractions,
  diagnostics,
  ambientNotices,
  lifecycleState,
  composerMode,
  onModeChange,
  personaId,
  onAvatarClick,
  onAddTarget,
  onAttachAction,
  targetToAppend,
  onTargetConsumed,
  actionAttachment,
  onActionAttach,
  onActionDetach,
  onSubmitAction,
  pendingActionIds,
  detachedActionIds,
  onPoseSubmitted,
  onReply,
  replyTarget,
  onCancelReply,
  draftScopePrefix,
  roomId,
  roomName,
  isAtPlace,
  currentPlaceId,
  currentPlaceName,
  placeBar,
  tavernGameWidget,
  speakerQueueBar,
  pendingAttachments,
  conversationTabs,
  speakingAs,
  reference,
  targetPoseId,
  onReturnToLive,
  referenceUnavailable,
  referenceLoading = false,
  referenceRetryable = false,
  onRetryReference,
}: GameWindowProps) {
  // #3784 — which conversation the composer's draft belongs to, held stable
  // while that conversation's storage key settles. The room-anchor composer
  // keeps one identity whether or not the room id has arrived yet; a
  // conversation tab is its own audience and is identified by its own key.
  const draftConversation = conversationTabs?.activeKey ?? ROOM_ANCHOR_CONVERSATION;
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  const { sessions, active } = useAppSelector((state) => state.game);
  const selectCharacter = useSelectCharacterMutation();

  // #2165 per-tab scroll: remember each tab's scroll offset, restore on
  // switch, and stick to bottom while the reader is already at the bottom
  // (adapted from ChatWindow's autoScroll pattern).
  const feedScrollRef = useRef<HTMLDivElement>(null);
  const scrollPositionsRef = useRef(new Map<string, number>());
  const pinnedRef = useRef(true);
  const activeConvKey = conversationTabs?.activeKey ?? 'room';
  const interactionCount = sceneFeed?.interactions.length ?? 0;
  // Threads and Chronological keep their OWN anchor slot (#3759 review
  // finding I5) -- this bypass must check whichever mode is CURRENTLY
  // active, not a single shared `anchor` field that no longer exists.
  const { preferences } = usePlayPreferences();
  const activeModeAnchor = preferences.readerMode === 'chronological' ? 'chronological' : 'threads';

  useEffect(() => {
    const el = feedScrollRef.current;
    if (!el) return;
    const saved = scrollPositionsRef.current.get(activeConvKey);
    // ThreadedNarrativeReader.tsx owns restoring its own pose-identity anchor
    // (#3759 Decision #3) for the room view -- this raw-scrollTop bookkeeping
    // must not fight it on the FIRST visit to the room view this session
    // (`saved === undefined`, i.e. this Map has never recorded a 'room'
    // position yet): the `else` branch below would otherwise unconditionally
    // jump to the bottom, which runs right after the anchor restore on first
    // mount (child effects fire before parent effects) and undoes it.
    //
    // Scoped to "no `saved` entry yet" rather than "an anchor exists at all"
    // (#3759 review finding I2): once the reader has restored (or the user
    // has scrolled) even once, a real scroll event records a 'room' entry
    // here (see handleFeedScroll below) -- from that point on this effect's
    // normal `saved` branch is what should run on every return to the room
    // tab, exactly like every other tab, so #2165's per-tab memory keeps
    // working rather than being permanently disabled the first time any
    // anchor is ever saved for this scene.
    if (
      activeConvKey === 'room' &&
      saved === undefined &&
      sceneFeed &&
      loadConversationAnchor(sceneFeed.sceneId)?.anchors?.[activeModeAnchor]
    ) {
      pinnedRef.current = false;
    } else if (saved !== undefined) {
      el.scrollTop = saved;
      pinnedRef.current = el.scrollHeight - saved - el.clientHeight < 8;
    } else {
      el.scrollTop = el.scrollHeight;
      pinnedRef.current = true;
    }
    // Prune scroll offsets for tabs that are no longer open (#2165 review
    // fold-in) — otherwise a closed tab's entry lingers in the map forever.
    const liveKeys = new Set(['room', ...(conversationTabs?.tabs.map((t) => t.key) ?? [])]);
    for (const key of scrollPositionsRef.current.keys()) {
      if (!liveKeys.has(key)) scrollPositionsRef.current.delete(key);
    }
    // Deliberately NOT depending on the whole `sceneFeed` object -- GamePage.tsx
    // builds a fresh `sceneFeed` object every render (new interactions array
    // included), so that would re-run this effect (and its scrollTop writes)
    // on every unrelated re-render instead of only on an actual tab switch or
    // scene change. `sceneFeed?.sceneId` is stable across those.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConvKey, conversationTabs?.tabs, sceneFeed?.sceneId]);

  useEffect(() => {
    const el = feedScrollRef.current;
    if (el && pinnedRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [interactionCount, activeConvKey]);

  const handleFeedScroll = () => {
    // Never record a position while browsing a historical reference (#3759
    // review finding I5): the reference view falls back `activeConvKey` to
    // 'room' (`conversationTabs` is undefined in reference mode), so without
    // this guard a reference-mode scroll would corrupt the room tab's own
    // remembered raw offset under that same key -- and unlike the
    // downstream bypass in the effect above (which only masks the symptom
    // once ANY anchor already exists), this fixes the corruption at the
    // source, including for a scene that has no anchor saved yet at all.
    if (reference) return;
    const el = feedScrollRef.current;
    if (!el) return;
    scrollPositionsRef.current.set(activeConvKey, el.scrollTop);
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
  };

  if (characters.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <p className="text-sm">
          You have no active characters. Visit the{' '}
          <Link to="/roster" className="underline">
            roster
          </Link>{' '}
          to apply for one.
        </p>
      </div>
    );
  }

  // #3412 review fix: `active` can now be hydrated from the server on a hard
  // reload with no `sessions[active]` entry yet — selection isn't presence,
  // so hydration never starts a session. Treat "active but not connected
  // yet" the same as "no active" here (GameTopBar's active avatar is the
  // affordance to actually connect); every access below this line can
  // otherwise assume `session` exists.
  const session = active ? sessions[active] : undefined;
  if (!active || !session) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="max-w-md rounded-lg border border-dashed p-8 text-center">
          <h1 className="font-serif text-2xl">Enter the world</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Choose a character above to begin. Your surroundings and story will appear here.
          </p>
        </div>
      </div>
    );
  }

  const sessionNames = Object.keys(sessions);
  const awaitingRoom = !session.room && !sceneFeed;
  const effectiveLifecycle =
    lifecycleState ??
    session.lifecycleState ??
    (!session.isConnected && session.room ? 'reconnecting' : undefined);
  const visibleDiagnostics = diagnostics ?? session.diagnostics ?? [];
  const playReady =
    session.isConnected &&
    Boolean(session.room) &&
    (!effectiveLifecycle ||
      ['ready-no-scene', 'ready-scene', 'encounter', 'aftermath'].includes(effectiveLifecycle));

  const handleTabClick = (name: MyRosterEntry['name']) => {
    // #3412 — persist the selection server-side ALONGSIDE the existing
    // puppeting behavior below, never replacing it.
    const entryId = characters.find((c) => c.name === name)?.id;
    if (entryId !== undefined) {
      selectCharacter.mutate(entryId);
    }
    dispatch(setActiveSession(name));
    if (!sessions[name].isConnected) {
      connect(name);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {reference && (
        <div
          className="flex shrink-0 items-center justify-between gap-3 border-b bg-amber-500/10 px-4 py-2 text-sm"
          role="status"
        >
          {/* #3759 Wave 9 review finding, section 5: demo copy reads "Reading
              history · read-only" -- adds that suffix here (one-line change,
              the string isn't otherwise composed/parameterized). */}
          <span>Reading history · {reference.title} · read-only</span>
          <button
            type="button"
            className="rounded border px-3 py-1 text-xs font-medium"
            onClick={onReturnToLive}
          >
            Return to live
          </button>
        </div>
      )}
      {awaitingRoom && (
        <div
          className="shrink-0 border-b bg-muted/30 px-4 py-2 text-xs text-muted-foreground"
          role="status"
        >
          {session.isConnected
            ? 'Entering the world… waiting for a confirmed location. You can write while you wait.'
            : 'Connection lost. Your draft is safe; you can keep writing while we reconnect.'}
        </div>
      )}
      {!awaitingRoom &&
        (effectiveLifecycle === 'reconnecting' ||
          (effectiveLifecycle === 'entering' && Boolean(session.room))) && (
          <div
            className="shrink-0 border-b bg-muted/30 px-4 py-2 text-xs text-muted-foreground"
            role="status"
          >
            {effectiveLifecycle === 'entering'
              ? 'Refreshing your confirmed location before play resumes…'
              : 'Connection lost. Your confirmed story remains available while we reconnect.'}
          </div>
        )}
      {visibleDiagnostics.length > 0 && (
        <aside
          className="shrink-0 border-b border-destructive/40 bg-destructive/5 px-4 py-2 text-sm"
          role="alert"
          aria-label="Connection notices"
        >
          <strong>Connection notice:</strong> {visibleDiagnostics[visibleDiagnostics.length - 1]}
        </aside>
      )}
      {sessionNames.length >= 2 && (
        <div className="mb-2 flex gap-2 border-b">
          {sessionNames.map((name) => {
            // #3774 -- same server-plus-delta combination as GameTopBar's
            // avatar row (canonical version lives in `characterAttention`,
            // frontend/src/game/attention.ts); the server baseline is what
            // makes the count right immediately after a switch, before this
            // session has seen anything new arrive.
            const char = characters.find((c) => c.name === name);
            const attention = characterAttention(char, sessions[name]);
            return (
              <button
                key={name}
                onClick={() => handleTabClick(name)}
                className={`relative rounded-t px-2 py-1 text-sm ${
                  active === name ? 'border-b-2 border-primary' : ''
                }`}
              >
                {name}
                {/* The active character's own attention already lives in
                    ConversationTabStrip's badges (#2166 review fold-in) — badging
                    its own already-highlighted puppet tab too is redundant/wrong. */}
                {name !== active && (
                  <AttentionBadge direct={attention.direct} ambient={attention.ambient} />
                )}
              </button>
            );
          })}
        </div>
      )}
      {sceneFeed && conversationTabs && <ConversationTabStrip {...conversationTabs} />}
      {sceneFeed ? (
        <>
          <div
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]"
            ref={feedScrollRef}
            onScroll={handleFeedScroll}
            data-testid="feed-scroll-container"
          >
            {referenceLoading && reference && (
              <div
                className="mx-auto my-8 max-w-md p-6 text-center text-muted-foreground"
                role="status"
              >
                Loading history…
              </div>
            )}
            {!referenceLoading && referenceUnavailable && reference && (
              <div
                className="mx-auto my-8 max-w-md rounded-lg border border-dashed p-6 text-center"
                role="alert"
              >
                <h2 className="font-serif text-xl">This pose is no longer available</h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  The requested history cannot be shown with your current access.
                </p>
                <button
                  type="button"
                  className="mt-4 rounded border px-3 py-2 text-sm"
                  onClick={onReturnToLive}
                >
                  Return to live
                </button>
              </div>
            )}
            {!referenceLoading && referenceRetryable && (
              <div
                className="mx-auto my-8 max-w-md rounded-lg border border-dashed p-6 text-center"
                role="alert"
              >
                <h2 className="font-serif text-xl">Couldn&apos;t load that history</h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  This may be a temporary connection problem.
                </p>
                <button
                  type="button"
                  className="mt-4 rounded border px-3 py-2 text-sm"
                  onClick={onRetryReference}
                >
                  Retry
                </button>
                <button
                  type="button"
                  className="mt-2 rounded border px-3 py-2 text-sm"
                  onClick={onReturnToLive}
                >
                  Return to live
                </button>
              </div>
            )}
            {!referenceLoading && !referenceUnavailable && !referenceRetryable && (
              <ThreadedNarrativeReader
                key={sceneFeed.sceneId}
                sceneId={sceneFeed.sceneId}
                conversationKey={sceneFeed.sceneId}
                // The REAL server-format conversation ref (#3759 review
                // finding C1) -- `reference.key` is already in that exact
                // shape (it's literally what's sent as the `conversation`
                // query param to fetch this reference), and matches
                // `_conversation()`'s own `scene:<id>` format for the live
                // room otherwise. Distinct from `conversationKey` above,
                // which stays the bare-id localStorage anchor/collapse key.
                conversationRef={reference ? reference.key : `scene:${sceneFeed.sceneId}`}
                interactions={sceneFeed.interactions}
                hasNextPage={sceneFeed.hasNextPage}
                fetchNextPage={sceneFeed.fetchNextPage}
                onAvatarClick={onAvatarClick}
                onAddTarget={onAddTarget}
                onAttachAction={onAttachAction}
                onReply={onReply}
                readOnly={Boolean(reference)}
                persistAnchor={activeConvKey === 'room'}
                targetPoseId={targetPoseId}
                isAtPlace={isAtPlace}
                currentPlaceId={currentPlaceId}
                currentPlaceName={currentPlaceName}
              />
            )}
          </div>
          {!reference && <SystemLane messages={session.messages} />}
        </>
      ) : (
        <ExplorationReader
          room={room ?? session.room}
          ambientInteractions={ambientInteractions ?? session.ambientInteractions}
          ambientNotices={ambientNotices ?? session.ambientNotices}
          lifecycleState={effectiveLifecycle}
          onRetry={() => {
            if (active) void connect(active);
          }}
        />
      )}
      {placeBar}
      {tavernGameWidget}
      {speakerQueueBar}
      {pendingAttachments}
      {reference ? (
        <div className="shrink-0 border-t bg-card px-4 py-3 text-center text-xs text-muted-foreground">
          Draft preserved for your live conversation
        </div>
      ) : (
        <CommandInput
          character={active}
          sceneId={sceneFeed?.sceneId}
          personaId={personaId}
          composerMode={composerMode}
          onModeChange={onModeChange}
          targetToAppend={targetToAppend}
          onTargetConsumed={onTargetConsumed}
          actionAttachment={actionAttachment}
          onActionAttach={onActionAttach}
          onActionDetach={onActionDetach}
          onSubmitAction={onSubmitAction}
          pendingActionIds={pendingActionIds}
          detachedActionIds={detachedActionIds}
          onPoseSubmitted={onPoseSubmitted}
          isAtPlace={isAtPlace}
          currentPlaceId={currentPlaceId}
          currentPlaceName={currentPlaceName}
          speakingAs={speakingAs}
          replyTarget={replyTarget}
          onCancelReply={onCancelReply}
          submitOnEnter={false}
          draftScope={`${draftScopePrefix ?? 'account'}:${active}:${conversationTabs?.activeKey ?? `room:${roomId ?? 'unknown'}`}`}
          // #3784 — the `room:unknown` placeholder above is not a room, it is
          // "the room we're standing in, not yet named": during entry the
          // client has no `room_state` yet. Saying so lets the draft move with
          // the scope when the id lands, instead of being stranded under the
          // placeholder while the composer re-hydrates an empty row
          // (`e2e/game-entry.spec.ts`). Naming the conversation alongside it is
          // what keeps the move within one audience: a tab opening before
          // `room_state` arrives changes the conversation, so the room pose
          // stays put instead of following into the whisper composer. (It does
          // then stay stranded under the placeholder for as long as that tab is
          // the active one -- no composer is mounted on the room anchor to carry
          // it -- which is the same outcome as before #3784 for that narrow
          // path, not a new loss.)
          draftScopeSettling={
            conversationTabs?.activeKey == null && roomId == null
              ? { provisional: true, conversation: draftConversation }
              : { conversation: draftConversation }
          }
          roomName={roomName}
          ready={playReady}
        />
      )}
    </div>
  );
}
