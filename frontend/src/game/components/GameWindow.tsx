import type { ReactNode, RefObject } from 'react';
import { useEffect, useMemo, useRef } from 'react';
import { ExplorationReader } from './ExplorationReader';
import type { GameLifecycleState, Session } from '@/store/gameSlice';
import type { FeedNote, InteractionWsPayload } from '@/hooks/types';
import type { RoomData } from './RoomPanel';
import { ThreadedNarrativeReader } from './ThreadedNarrativeReader';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';
import { ConversationTabStrip, type ConversationTabStripProps } from './ConversationTabStrip';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { Interaction } from '@/scenes/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import {
  dismissFeedItem,
  minimizeFeedItem,
  restoreFeedItem,
  setActiveSession,
  setBrowsingIdentity,
} from '@/store/gameSlice';
import { writeTabIdentity } from '@/store/browsingIdentity';
import { useSelectCharacterMutation } from '@/roster/queries';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Link } from 'react-router-dom';
import type { MyRosterEntry } from '@/roster/types';
import { characterAttention, chipUnread, type AttentionOptions } from '@/game/attention';
import { visibleInteractions, visibleNotes, wakingKinds } from '../feedChips';
import { FeedChipStrip } from './FeedChipStrip';
import { FeedBlockControlsContext, type FeedBlockControls } from '../feedBlockControls';
import { AttentionBadge } from '@/game/components/AttentionBadge';
import { loadConversationAnchor, usePlayPreferences } from '../playPreferences';
import { getNarrativeBody } from '../narrativeRetention';

/** The active scene's live feed, composed once by `GamePage` (#2156). */
export interface GameWindowSceneFeed {
  sceneId: string;
  interactions: Interaction[];
  hasNextPage?: boolean;
  fetchNextPage: () => void;
  retention?: { retained: number; evicted: number; warning: boolean; gap: boolean };
}

interface GameWindowProps {
  characters: MyRosterEntry[];
  /** Staff see the composer's Commands mode and the console (#3857). */
  isStaff?: boolean;
  /** The signed-in account, for the per-account play preferences the chips live in (#3856). */
  accountId?: number | null;
  /** When present, the center column renders the threaded scene reader. */
  sceneFeed?: GameWindowSceneFeed;
  /** Structured quiet-room data; absent only while entry is pending. */
  room?: RoomData | null;
  /** Scene-less interaction frames for the exploration reader. */
  ambientInteractions?: InteractionWsPayload[];
  diagnostics?: string[];
  /** Typed text lines (#3856); defaults to the session's own. */
  notes?: FeedNote[];
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
  onSubmitAction?: (action: ActionAttachmentInfo, clientRequestId?: string) => void;
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

interface GameWindowStatusProps {
  reference?: GameWindowProps['reference'];
  onReturnToLive?: () => void;
  awaitingRoom: boolean;
  effectiveLifecycle?: GameLifecycleState;
  session: Session;
  visibleDiagnostics: string[];
  sessionNames: string[];
  characters: MyRosterEntry[];
  active: string | null;
  sessions: Record<string, Session>;
  onTabClick: (name: MyRosterEntry['name']) => void;
  onRetryLocation: () => void;
  /** What the player's chips say should badge a puppet tab (#3856). */
  attentionOptionsFor: (name: string) => AttentionOptions;
}

function GameWindowStatus({
  reference,
  onReturnToLive,
  awaitingRoom,
  effectiveLifecycle,
  session,
  visibleDiagnostics,
  sessionNames,
  characters,
  active,
  sessions,
  onTabClick,
  onRetryLocation,
  attentionOptionsFor,
}: GameWindowStatusProps) {
  const entryCopy = session.isConnected
    ? 'Connected, but your location has not been confirmed yet.'
    : 'Connection lost. Your draft is safe while we reconnect.';
  let retryLabel = 'Reconnect';
  if (session.roomStateResyncStatus === 'pending') {
    retryLabel = 'Refreshing…';
  } else if (session.isConnected) {
    retryLabel = 'Refresh location';
  }

  return (
    <>
      {reference && (
        <div
          className="flex shrink-0 items-center justify-between gap-3 border-b bg-amber-500/10 px-4 py-2 text-sm"
          role="status"
        >
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
          className="flex shrink-0 flex-wrap items-center gap-2 border-b bg-muted/30 px-4 py-2 text-xs text-muted-foreground"
          role="status"
        >
          <span>{entryCopy}</span>
          <button
            type="button"
            className="rounded border px-2 py-1 font-medium text-foreground"
            onClick={onRetryLocation}
            disabled={session.roomStateResyncStatus === 'pending'}
          >
            {retryLabel}
          </button>
          <Link to="/hall" className="rounded border px-2 py-1 font-medium text-foreground">
            Return to Hall
          </Link>
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
      <CharacterTabs
        sessionNames={sessionNames}
        characters={characters}
        active={active}
        sessions={sessions}
        onTabClick={onTabClick}
        attentionOptionsFor={attentionOptionsFor}
      />
    </>
  );
}

function CharacterTabs({
  sessionNames,
  characters,
  active,
  sessions,
  onTabClick,
  attentionOptionsFor,
}: Pick<
  GameWindowStatusProps,
  'sessionNames' | 'characters' | 'active' | 'sessions' | 'onTabClick' | 'attentionOptionsFor'
>) {
  if (sessionNames.length < 2) return null;
  return (
    <div className="mb-2 flex gap-2 border-b">
      {sessionNames.map((name) => {
        const char = characters.find((c) => c.name === name);
        const attention = characterAttention(char, sessions[name], attentionOptionsFor(name));
        return (
          <button
            key={name}
            onClick={() => onTabClick(name)}
            className={`relative rounded-t px-2 py-1 text-sm ${
              active === name ? 'border-b-2 border-primary' : ''
            }`}
          >
            {name}
            {name !== active && (
              <AttentionBadge direct={attention.direct} ambient={attention.ambient} />
            )}
          </button>
        );
      })}
    </div>
  );
}

type GameWindowFeedProps = Pick<
  GameWindowProps,
  | 'accountId'
  | 'sceneFeed'
  | 'conversationTabs'
  | 'reference'
  | 'referenceLoading'
  | 'referenceUnavailable'
  | 'referenceRetryable'
  | 'onReturnToLive'
  | 'onRetryReference'
  | 'room'
  | 'ambientInteractions'
  | 'notes'
  | 'onAvatarClick'
  | 'onAddTarget'
  | 'onAttachAction'
  | 'onReply'
  | 'targetPoseId'
  | 'isAtPlace'
  | 'currentPlaceId'
  | 'currentPlaceName'
> & {
  activeConvKey: string;
  feedScrollRef: RefObject<HTMLDivElement>;
  /** The chip strip above the column (#3856); absent in a reference view. */
  chipStrip?: ReactNode;
  /** True while the All switch is off: the column shows one line instead of a reader. */
  allOff?: boolean;
  onFeedScroll: () => void;
  session: Session;
  effectiveLifecycle?: GameLifecycleState;
  active: string | null;
  connect: (character: string) => Promise<void>;
};

function GameWindowFeed({
  accountId,
  sceneFeed,
  conversationTabs,
  reference,
  referenceLoading = false,
  referenceUnavailable = false,
  referenceRetryable = false,
  onReturnToLive,
  onRetryReference,
  activeConvKey,
  feedScrollRef,
  onFeedScroll,
  chipStrip,
  allOff = false,
  session,
  room,
  ambientInteractions,
  notes,
  effectiveLifecycle,
  active,
  connect,
  onAvatarClick,
  onAddTarget,
  onAttachAction,
  onReply,
  targetPoseId,
  isAtPlace,
  currentPlaceId,
  currentPlaceName,
}: GameWindowFeedProps) {
  if (allOff) {
    return (
      <>
        {chipStrip}
        {sceneFeed && conversationTabs && <ConversationTabStrip {...conversationTabs} />}
        <div
          className="min-h-0 flex-1 overflow-y-auto px-6 py-8 text-sm italic text-muted-foreground"
          data-testid="feed-all-off"
        >
          Everything is switched off. Press a chip to bring one kind back.
        </div>
      </>
    );
  }

  return (
    <>
      {chipStrip}
      {sceneFeed && conversationTabs && <ConversationTabStrip {...conversationTabs} />}
      {sceneFeed ? (
        <>
          <div
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]"
            ref={feedScrollRef}
            onScroll={onFeedScroll}
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
              <section aria-label="Roleplay" data-testid="authoritative-rp-block">
                <ThreadedNarrativeReader
                  key={sceneFeed.sceneId}
                  sceneId={sceneFeed.sceneId}
                  accountId={accountId}
                  conversationKey={sceneFeed.sceneId}
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
                  // A reference view reads history; the live column's notes are
                  // this session's own and do not belong in it (#3856).
                  notes={reference ? undefined : (notes ?? session.notes)}
                />
              </section>
            )}
          </div>
        </>
      ) : (
        <ExplorationReader
          room={room ?? session.room}
          ambientInteractions={ambientInteractions ?? session.ambientInteractions}
          notes={notes ?? session.notes}
          lifecycleState={effectiveLifecycle}
          onRetry={() => {
            if (active) void connect(active);
          }}
        />
      )}
    </>
  );
}

export function GameWindow({
  characters,
  isStaff = false,
  accountId = null,
  sceneFeed,
  room,
  ambientInteractions,
  diagnostics,
  notes,
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
  const { connect, requestRoomState } = useGameSocket();
  const selectCharacter = useSelectCharacterMutation();
  const { sessions, active } = useAppSelector((state) => state.game);

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
  const { preferences } = usePlayPreferences(accountId);
  const activeModeAnchor = preferences.readerMode === 'chronological' ? 'chronological' : 'threads';
  // The chips (#3856) live in the per-account preferences, the store
  // DisplaySettings writes; the readerMode read above predates that and keeps
  // its own key. Every hook here runs before the early returns below.
  const { preferences: chipPreferences, update: updateChipPreferences } =
    usePlayPreferences(accountId);
  const chipState = useMemo(
    () => ({ chips: chipPreferences.feedChips, all: chipPreferences.feedAll }),
    [chipPreferences.feedChips, chipPreferences.feedAll]
  );
  const waking = useMemo(() => wakingKinds(chipState.chips), [chipState.chips]);
  const activeSessionForFeed = active ? sessions[active] : undefined;
  const dismissedKeys = useMemo(
    () => new Set(activeSessionForFeed?.dismissedFeed ?? []),
    [activeSessionForFeed?.dismissedFeed]
  );
  const minimizedKeys = useMemo(
    () => new Set(activeSessionForFeed?.minimizedFeed ?? []),
    [activeSessionForFeed?.minimizedFeed]
  );
  // A reference view reads history as it was; chips and dismissals apply to
  // the live column only.
  const visibleSceneFeed = useMemo(() => {
    if (!sceneFeed || reference) return sceneFeed;
    const interactions = visibleInteractions(sceneFeed.interactions, chipState, dismissedKeys);
    return interactions === sceneFeed.interactions ? sceneFeed : { ...sceneFeed, interactions };
  }, [sceneFeed, reference, chipState, dismissedKeys]);
  const visibleAmbient = useMemo(() => {
    const items = ambientInteractions ?? activeSessionForFeed?.ambientInteractions ?? [];
    const hydrated = items.map((item) => ({
      ...item,
      content: item.content || getNarrativeBody(item)?.content || '',
      line: item.line || getNarrativeBody(item)?.line,
    }));
    return visibleInteractions(hydrated, chipState, dismissedKeys);
  }, [ambientInteractions, activeSessionForFeed?.ambientInteractions, chipState, dismissedKeys]);
  const visibleNoteList = useMemo(() => {
    const items = notes ?? activeSessionForFeed?.notes ?? [];
    return visibleNotes(items, chipState, dismissedKeys);
  }, [notes, activeSessionForFeed?.notes, chipState, dismissedKeys]);
  const newCounts = useMemo(
    () =>
      activeSessionForFeed
        ? chipUnread(activeSessionForFeed, personaId, chipState.chips, dismissedKeys)
        : {},
    [activeSessionForFeed, personaId, chipState.chips, dismissedKeys]
  );
  const blockControls = useMemo<FeedBlockControls>(
    () => ({
      minimized: minimizedKeys,
      minimize: (key) => active && dispatch(minimizeFeedItem({ character: active, key })),
      restore: (key) => active && dispatch(restoreFeedItem({ character: active, key })),
      dismiss: (key) => active && dispatch(dismissFeedItem({ character: active, key })),
    }),
    [minimizedKeys, active, dispatch]
  );
  const attentionOptionsFor = (name: string): AttentionOptions => ({
    wakingKinds: waking,
    dismissed: new Set(sessions[name]?.dismissedFeed ?? []),
  });

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
      loadConversationAnchor(sceneFeed.sceneId, accountId)?.anchors?.[activeModeAnchor]
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

  const handleTabClick = async (name: MyRosterEntry['name']) => {
    // #3479 decision 4: a puppet-tab switch is tab-local. It writes THIS
    // tab's browsing identity (sessionStorage + the gameSlice mirror) and
    // touches no other tab. The durable account selection is written only
    // when the switch opens a socket, and before it: login puppets the
    // server's durable selection as the socket authenticates (#3812,
    // ADR-0294), and puppeting records the selection anyway, so this is the
    // same fact landed a moment earlier. GameTopBar.handleSelectCharacter
    // carries the long form of this rule.
    const entryId = characters.find((c) => c.name === name)?.id;
    if (entryId !== undefined) {
      writeTabIdentity(entryId);
      dispatch(setBrowsingIdentity(entryId));
    }
    dispatch(setActiveSession(name));
    if (!sessions[name].isConnected) {
      if (entryId !== undefined) {
        try {
          await selectCharacter.mutateAsync(entryId);
        } catch {
          // onError already toasted; the connect below still carries the intent.
        }
      }
      connect(name);
    }
  };

  return (
    <FeedBlockControlsContext.Provider value={reference ? null : blockControls}>
      <div className="flex min-h-0 flex-1 flex-col">
        <GameWindowStatus
          reference={reference}
          onReturnToLive={onReturnToLive}
          awaitingRoom={awaitingRoom}
          effectiveLifecycle={effectiveLifecycle}
          session={session}
          visibleDiagnostics={visibleDiagnostics}
          sessionNames={sessionNames}
          characters={characters}
          active={active}
          sessions={sessions}
          onTabClick={handleTabClick}
          onRetryLocation={() => {
            if (!active) return;
            if (session.isConnected) {
              requestRoomState(active);
            } else {
              connect(active).catch(() => {});
            }
          }}
          attentionOptionsFor={attentionOptionsFor}
        />
        <GameWindowFeed
          accountId={accountId}
          sceneFeed={visibleSceneFeed}
          chipStrip={
            !reference && (
              <FeedChipStrip
                state={chipState}
                onChange={(next) =>
                  updateChipPreferences({ feedChips: next.chips, feedAll: next.all })
                }
                newCounts={newCounts}
              />
            )
          }
          allOff={!reference && !chipState.all}
          conversationTabs={conversationTabs}
          reference={reference}
          referenceLoading={referenceLoading}
          referenceUnavailable={referenceUnavailable}
          referenceRetryable={referenceRetryable}
          onReturnToLive={onReturnToLive}
          onRetryReference={onRetryReference}
          activeConvKey={activeConvKey}
          feedScrollRef={feedScrollRef}
          onFeedScroll={handleFeedScroll}
          session={session}
          room={room}
          ambientInteractions={visibleAmbient}
          notes={visibleNoteList}
          effectiveLifecycle={effectiveLifecycle}
          active={active}
          connect={connect}
          onAvatarClick={onAvatarClick}
          onAddTarget={onAddTarget}
          onAttachAction={onAttachAction}
          onReply={onReply}
          targetPoseId={targetPoseId}
          isAtPlace={isAtPlace}
          currentPlaceId={currentPlaceId}
          currentPlaceName={currentPlaceName}
        />
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
            // Enter sends, Shift+Enter breaks the line (#3818) — the convention
            // of every chat RP interface; the reviewer found Enter-as-newline
            // and a reach for the Send button slower than typing. This was
            // `submitOnEnter={false}` (Cmd/Ctrl+Enter to send) since the
            // narrative composer landed. Ctrl/Cmd+Enter still sends too.
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
            isStaff={isStaff}
          />
        )}
      </div>
    </FeedBlockControlsContext.Provider>
  );
}
