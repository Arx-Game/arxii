import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ComponentProps } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { GameLayout } from './components/GameLayout';
import { GameTopBar } from './components/GameTopBar';
import { GameWindow } from './components/GameWindow';
import { CharacterCardDrawer } from './components/CharacterCardDrawer';
import { PlaySidebar, type SidebarMode } from './components/PlaySidebar';
import { fetchPlayContext, fetchPlayPoses, PlayFetchError } from './playQueries';
import type { PlayPage } from './playTypes';
import { FocusPanel } from './components/FocusPanel';
import { SidebarTabPanel } from './components/SidebarTabPanel';
import { DreamspacePanel } from '@/dreams/components/DreamspacePanel';
import { dreamKeys, useDreamState } from '@/dreams/queries';
import { useActionResult } from '@/hooks/actionResultBus';
import type { ActionResultPayload } from '@/hooks/types';
import { PresencePanel } from './components/PresencePanel';
import { CeremonyRoomCard } from '@/ceremonies/CeremonyRoomCard';
import { EventsSidebarPanel } from '@/events/components/EventsSidebarPanel';
import { useEncounterForScene, combatKeys } from '@/combat/queries';
import { CombatRail } from '@/combat/components/CombatRail';
import { useBattleForSceneQuery } from '@/battles/queries';
import { StoryTray } from '@/missions/components/StoryTray';
import { JournalTab } from '@/journals/components/JournalTab';
import { StatusPanel } from '@/status/components/StatusPanel';
import { InventorySidebarPanel } from '@/inventory/components/InventorySidebarPanel';
import { VoyagePanel } from '@/travel/components/VoyagePanel';
import { actingPersonaId } from '@/roster/persona';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useFocusStack, type FocusEntry } from '@/inventory/hooks/useFocusStack';
import { Link, useSearchParams } from 'react-router-dom';
import { useAccount } from '@/store/hooks';
import { useAppSelector, useAppDispatch } from '@/store/hooks';
import type { AppDispatch } from '@/store/store';
import { useGameSocket } from '@/hooks/useGameSocket';
import {
  markThreadSeen,
  setSceneBaseline,
  openThreadTab,
  closeThreadTab,
  setActiveThreadTab,
  hydrateThreadTabs,
  startSession,
} from '@/store/gameSlice';
import { loadThreadTabs, saveThreadTabs } from './threadTabsStorage';
import { useSceneInteractions } from '@/scenes/hooks/useSceneInteractions';
import { useThreading, getThreadKey } from '@/scenes/hooks/useThreading';
import type { Thread } from '@/scenes/hooks/useThreading';
import { threadToComposerMode, tabKeyToComposerMode } from '@/scenes/hooks/threadToComposerMode';
import { usePendingUnlinkedActions } from '@/scenes/hooks/usePendingUnlinkedActions';
import { ConsentPrompt } from '@/scenes/components/ConsentPrompt';
import { PlaceBar } from '@/scenes/components/PlaceBar';
import { TavernGameWidget } from '@/scenes/components/TavernGameWidget';
import { SpeakerQueueBar } from '@/scenes/components/SpeakerQueueBar';
import { ActionPanel } from '@/scenes/components/ActionPanel';
import { PendingActionAttachments } from '@/scenes/components/PendingActionAttachments';
import { createActionRequest, fetchPlaces } from '@/scenes/actionQueries';
import { fetchScene } from '@/scenes/queries';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import type { Interaction, SceneDetail } from '@/scenes/types';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import type { ComposerMode } from './components/CommandInput';
import type { ConversationTabStripProps } from './components/ConversationTabStrip';

const DEFAULT_ROOM_ENTRY: FocusEntry = {
  kind: 'room',
  room: null,
  sceneSummary: null,
};

// Stable empty-object reference so `useThreading`'s memo doesn't see a "changed"
// lastSeenByThread on every render when there's no active session yet (#2156).
const EMPTY_THREAD_LAST_SEEN: Record<string, number> = {};
// Stable empty-array reference (#2165) — same reasoning as EMPTY_THREAD_LAST_SEEN.
const EMPTY_OPEN_TABS: string[] = [];

/**
 * Derive the tab label from the current focus entry, falling back to the
 * room name (or "Room" when there's no active session yet).
 */
function deriveRoomTabLabel(focus: FocusEntry, roomName: string | undefined): string {
  switch (focus.kind) {
    case 'room':
      return focus.room?.name ?? roomName ?? 'Room';
    case 'character':
      return focus.character.name;
    case 'item':
      return focus.item.name;
    default:
      return 'Room';
  }
}

/** Map the open thread keys onto the conversation strip's tab descriptors. */
function buildTabDescriptors(openThreadTabs: string[], threads: Thread[]) {
  return openThreadTabs.map((key) => {
    const thread = threads.find((t) => t.key === key);
    return {
      key,
      label: thread?.label ?? (key.startsWith('place:') ? 'Place' : 'Whisper'),
      unreadCount: thread?.unreadCount ?? 0,
    };
  });
}

/** The composer mode the room anchor resets to when its tab is selected. */
function roomComposerMode(threads: Thread[], roomName: string): ComposerMode {
  const roomThread = threads.find((t) => t.key === 'room');
  return roomThread
    ? threadToComposerMode(roomThread, roomName)
    : { command: 'pose', targets: [], label: `Pose → ${roomName}` };
}

/**
 * Hydrate the scene's saved thread-tab layout once, then persist later changes.
 *
 * #2165 tab-layout persistence (spec decision 5a). Hydration runs once per
 * character+scene, BEFORE the save effect may write. This used to be a ref
 * handshake, but a ref is set synchronously the instant hydration is
 * *attempted*: the save effect runs in the same commit right after, while its
 * closure still holds the pre-hydration `openThreadTabs: []`, so it wrote (and
 * pruned) an empty layout over the entry just loaded. That self-healed on the
 * next render UNLESS the user switched character/scene first (A->B->A), leaving
 * the empty write durable. Using React state instead means `setTabsReadyFor`
 * and the `hydrateThreadTabs` dispatch land in the same batched re-render, so
 * the save effect's first run for a key is the POST-hydration commit, with
 * hydrated values in the closure. The save is gated on hydration having
 * LANDED, not attempted.
 */
function useThreadTabPersistence(
  active: string | null,
  sceneId: string | undefined,
  openThreadTabs: string[],
  activeThreadTabRaw: string | null,
  accountId?: number | null
) {
  const dispatch = useAppDispatch();
  const [tabsReadyFor, setTabsReadyFor] = useState<string | null>(null);
  useEffect(() => {
    if (!active || !sceneId) return;
    const hydrationKey = `${accountId ?? 'anonymous'}:${active}:${sceneId}`;
    if (tabsReadyFor === hydrationKey) return;
    const stored = loadThreadTabs(active, sceneId, accountId);
    if (stored && stored.openThreadTabs.length > 0) {
      dispatch(hydrateThreadTabs({ character: active, ...stored }));
    }
    setTabsReadyFor(hydrationKey);
  }, [active, sceneId, dispatch, tabsReadyFor, accountId]);

  useEffect(() => {
    if (!active || !sceneId) return;
    if (tabsReadyFor !== `${accountId ?? 'anonymous'}:${active}:${sceneId}`) return;
    saveThreadTabs(
      active,
      sceneId,
      {
        openThreadTabs,
        activeThreadTab: activeThreadTabRaw,
      },
      accountId
    );
  }, [active, sceneId, openThreadTabs, activeThreadTabRaw, tabsReadyFor, accountId]);
}

/** The feed props GameWindow takes, present only when we are inside a scene. */
function sceneFeedProps(
  sceneId: string | undefined,
  interactions: ComponentProps<typeof GameWindow>['sceneFeed'] extends infer T
    ? T extends { interactions: infer I }
      ? I
      : never
    : never,
  hasNextPage: boolean,
  fetchNextPage: () => void
): ComponentProps<typeof GameWindow>['sceneFeed'] {
  if (!sceneId) return undefined;
  return { sceneId, interactions, hasNextPage, fetchNextPage };
}

/** How the composer labels the speaker, when a character is assumed. */
function speakingAsProps(
  entry: { name: string; profile_picture_url?: string | null } | null
): ComponentProps<typeof GameWindow>['speakingAs'] {
  if (!entry) return undefined;
  return { name: entry.name, thumbnailUrl: entry.profile_picture_url ?? null };
}

/** The three widgets that only exist while standing in a place. */
function placeWidgets(
  placesRoomId: string | null | undefined,
  character: string | null,
  currentPlaceId: number | null
) {
  if (!placesRoomId || !character) return {};
  return {
    placeBar: (
      <PlaceBar sceneId={placesRoomId} character={character} currentPlaceId={currentPlaceId} />
    ),
    tavernGameWidget: <TavernGameWidget roomId={placesRoomId} />,
    speakerQueueBar: <SpeakerQueueBar roomId={placesRoomId} />,
  };
}

interface GameRightSidebarProps {
  roomTabLabel: string;
  isDreaming: boolean;
  activeCharacterId: number | null;
  active: string | null;
  focus: ComponentProps<typeof FocusPanel>['focus'];
  roomData: ComponentProps<typeof FocusPanel>['roomData'];
  sceneData: ComponentProps<typeof FocusPanel>['sceneData'];
  hasActiveEncounter: boolean;
  hasActiveBattle: boolean;
  showCombatRail: boolean;
  railEncounterId: number;
  combatSceneDetail?: SceneDetail;
  onDismissOutcome: () => void;
  activeTab: string;
  onTabChange: (tab: string) => void;
}

/** The right-hand tab rail: room/focus, stories, events, presence, sheet panels. */
function GameRightSidebar({
  roomTabLabel,
  isDreaming,
  activeCharacterId,
  active,
  focus,
  roomData,
  sceneData,
  hasActiveEncounter,
  hasActiveBattle,
  showCombatRail,
  railEncounterId,
  combatSceneDetail,
  onDismissOutcome,
  activeTab,
  onTabChange,
}: GameRightSidebarProps) {
  return (
    <SidebarTabPanel
      activeTab={activeTab}
      onTabChange={onTabChange}
      roomTabLabel={roomTabLabel}
      roomPanel={
        isDreaming && activeCharacterId && active ? (
          <DreamspacePanel characterId={activeCharacterId} characterName={active} />
        ) : (
          <>
            <FocusPanel
              focus={focus}
              roomCharacter={active}
              roomData={roomData}
              sceneData={sceneData}
              hasActiveEncounter={hasActiveEncounter}
              hasActiveBattle={hasActiveBattle}
            />
            {sceneData && showCombatRail && (
              <CombatRail
                sceneId={sceneData.id}
                encounterId={railEncounterId}
                viewerCanGm={combatSceneDetail?.viewer_can_gm ?? false}
                scene={combatSceneDetail}
                onDismissOutcome={onDismissOutcome}
              />
            )}
          </>
        )
      }
      storiesPanel={<StoryTray roomKey={roomData?.name ?? 'nowhere'} />}
      eventsPanel={
        <>
          <CeremonyRoomCard roomId={roomData ? String(roomData.id) : undefined} />
          <EventsSidebarPanel />
        </>
      }
      presencePanel={<PresencePanel />}
      statusPanel={
        activeCharacterId ? (
          <StatusPanel characterId={activeCharacterId} characterName={active ?? undefined} />
        ) : undefined
      }
      inventoryPanel={
        activeCharacterId ? <InventorySidebarPanel characterId={activeCharacterId} /> : undefined
      }
      journalPanel={<JournalTab />}
      travelPanel={activeCharacterId ? <VoyagePanel characterId={activeCharacterId} /> : undefined}
    />
  );
}

/** Start the selected session once when the game page first mounts. */
function useAutoStartSession(
  active: string | null,
  sessions: Record<string, unknown>,
  dispatch: AppDispatch,
  connect: (name: string) => Promise<unknown>
): void {
  const autoStartSpent = useRef(false);
  const hasActiveSession = active ? Boolean(sessions[active]) : false;
  useEffect(() => {
    if (!active || autoStartSpent.current) return;
    autoStartSpent.current = true;
    if (hasActiveSession) return;
    dispatch(startSession(active));
    connect(active).catch(() => {});
  }, [active, hasActiveSession, dispatch, connect]);
}

interface SceneThreadStateSyncArgs {
  sceneId: string | undefined;
  active: string | null;
  sceneBaselineId: number | null | undefined;
  allInteractions: Interaction[];
  activeThreadTab: string | null;
  resetForNewScene: () => void;
  setComposerMode: (mode: undefined) => void;
  setReplyTarget: (target: Interaction | null) => void;
  dispatch: AppDispatch;
}

/** Keep scene baselines, thread filters, composer state, and read cursors in sync. */
function useSceneThreadStateSync({
  sceneId,
  active,
  sceneBaselineId,
  allInteractions,
  activeThreadTab,
  resetForNewScene,
  setComposerMode,
  setReplyTarget,
  dispatch,
}: SceneThreadStateSyncArgs): void {
  useEffect(() => {
    if (!sceneId || !active || sceneBaselineId != null) return;
    let maxId: number | undefined;
    for (const interaction of allInteractions) {
      const id = Number(interaction.id);
      if (maxId === undefined || id > maxId) maxId = id;
    }
    dispatch(setSceneBaseline({ character: active, baselineId: maxId ?? 0 }));
  }, [sceneId, active, sceneBaselineId, allInteractions, dispatch]);

  useEffect(() => {
    resetForNewScene();
  }, [active, sceneId, resetForNewScene]);

  useEffect(() => {
    setComposerMode(undefined);
    setReplyTarget(null);
  }, [active, sceneId, setComposerMode, setReplyTarget]);

  useEffect(() => {
    if (!sceneId || !active || document.visibilityState === 'hidden') return;
    const seenKey = activeThreadTab ?? 'room';
    let maxId: number | undefined;
    for (const interaction of allInteractions) {
      if (getThreadKey(interaction) !== seenKey) continue;
      const id = Number(interaction.id);
      if (!Number.isFinite(id) || id <= 0) continue;
      if (maxId === undefined || id > maxId) maxId = id;
    }
    const timer = window.setTimeout(() => {
      if (maxId !== undefined && document.visibilityState !== 'hidden') {
        dispatch(markThreadSeen({ character: active, threadKey: seenKey, interactionId: maxId }));
      }
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [sceneId, active, allInteractions, activeThreadTab, dispatch]);
}

interface GameCenterProps {
  sceneId?: string;
  accountId: number;
  activeCharacter?: string | null;
  gameWindow: ComponentProps<typeof GameWindow>;
}

function GameCenter({ sceneId, accountId, activeCharacter, gameWindow }: GameCenterProps) {
  return (
    <>
      {sceneId && <ConsentPrompt sceneId={sceneId} viewerKey={activeCharacter ?? undefined} />}
      <GameWindow {...gameWindow} draftScopePrefix={`account:${accountId}`} />
      {sceneId && <ActionPanel sceneId={sceneId} viewerKey={activeCharacter ?? undefined} />}
    </>
  );
}

export function GamePage() {
  const account = useAccount();
  const [searchParams, setSearchParams] = useSearchParams();
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  // #3774 -- the game screen is the one place that polls this. Focus and the
  // 60s timer are what make a badge clear on this device after the player read
  // the poses on another one; nothing pushes read state.
  const { data: characters = [] } = useMyRosterEntriesQuery({
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
  const { sessions, active } = useAppSelector((state) => state.game);

  // Enter-the-world auto-start (#3412): a fresh hydration (reload survival,
  // or arriving here via the header's docked chip) sets `active` with no
  // `sessions[active]` entry yet — until now, GameTopBar's clickable avatar
  // was the ONLY way to actually connect from that state, i.e. selecting a
  // character always cost a second click once you got to /game. This is the
  // ONE deliberate selection->presence crossing (selection precedes
  // puppeting): GamePage's own mount path auto-starts the session instead of
  // waiting for that click. Scoped strictly to "no session object exists
  // yet" (via the boolean below, not the raw `sessions` object, so the
  // effect doesn't re-run on every unrelated session mutation once started)
  // — once a session exists, reconnection on a drop is useGameSocket's own
  // backoff-driven job, and re-dispatching `startSession` here would zero
  // its accumulated `unread` count on every rerun. A session that already
  // exists (connected or not — e.g. GameTopBar was used to switch puppets
  // before this effect ever saw a gap) is therefore left entirely alone.
  // The crossing is once-per-mount: the ref spends the auto-start on the
  // FIRST session-less active name this mount observes (present at mount, or
  // arriving via the initial account hydration on a hard reload of /game).
  // Any LATER change of `active` while mounted — a cross-tab selection
  // surfacing through a focus refetch, a failed select POST reverting to the
  // server value — must not connect a session nobody asked this tab to start:
  // that would be selection summoning presence, which the state model forbids
  // outside this one mount-path crossing (ADR-0241). Switching puppets
  // mid-mount stays what it always was: GameTopBar's explicit avatar click.
  // The ref is spent on the first run that OBSERVES an active name at all —
  // whether or not a connect fires. A mount that finds a live session already
  // in place (SPA re-nav to /game while Redux still holds the connection) has
  // its world entry too; leaving the ref unspent there would let a later
  // cross-tab flip of `active` slip past the guard. Only null-before-hydration
  // runs leave the crossing unspent.
  useAutoStartSession(active, sessions, dispatch, connect);

  const focus = useFocusStack(DEFAULT_ROOM_ENTRY);

  // Resolve the active character name to its underlying ObjectDB pk (copied
  // from WardrobePage's snippet — CharacterSheet is OneToOne with ObjectDB
  // via primary_key=True, so the same id doubles as the character sheet pk).
  const activeEntry = useMemo(
    () => characters.find((entry) => entry.name === active) ?? null,
    [characters, active]
  );
  const activeCharacterId = activeEntry?.character_id ?? null;
  // Lifted from GameWindow (#2156 review fold-in) — dedupes the roster query
  // that both GamePage and GameWindow used to call independently.
  const personaId = actingPersonaId(activeEntry);
  // The active character's own RosterEntry id (#2156 Task 7) — the FriendButton's
  // `viewerEntryId` inside the character-card drawer.
  const viewerEntryId = activeEntry?.id ?? null;
  // Dreamspace takeover (#3003): the right sidebar's Room tab renders
  // DreamspacePanel instead of FocusPanel whenever the active character is
  // dreamside — the same rule the server already applies to `look` and the
  // `room_state` websocket push, so web and telnet agree by construction.
  const { data: dreamState } = useDreamState(activeCharacterId ?? 0);
  const isDreaming = Boolean(activeCharacterId && active && dreamState?.is_dreamside);

  // Dreamspace takeover trigger (#3003 review fix, finding 2): the global
  // query client's 5-minute `staleTime` (queryClient.ts) means `useDreamState`
  // above never refetches on its own — its only prior invalidator lived
  // inside `DreamspacePanel`, which isn't mounted until AFTER the takeover
  // has already happened, so falling asleep never re-triggered the check that
  // would swap `FocusPanel` for `DreamspacePanel`. Chose the `useActionResult`
  // bus over driving `isDreaming` off the `room_state` frame: `room_state`
  // (a) carries no `is_dreamside` field today, and (b) isn't re-sent when
  // Sleeping/Unconscious is applied (only movement re-sends it), so "driving
  // off it" would need new backend plumbing on both counts. The action-result
  // bus is the mechanism `DreamspacePanel` itself already relies on for this
  // exact purpose (see its own `handleActionResult` — "peril outcomes, forced
  // wakes, and a co-dreamer's arrival all surface without polling"); mirroring
  // it here at the GamePage level just gives entry the same trigger exit
  // already had, with no new backend surface.
  const dreamActionResultClient = useQueryClient();
  const handleDreamStateActionResult = useCallback(
    (_payload: ActionResultPayload) => {
      if (!activeCharacterId) return;
      dreamActionResultClient
        .invalidateQueries({ queryKey: dreamKeys.state(activeCharacterId) })
        .catch(() => {});
    },
    [activeCharacterId, dreamActionResultClient]
  );
  useActionResult(handleDreamStateActionResult);

  const activeSession = active ? sessions[active] : null;
  const roomData = activeSession?.room ?? null;
  const sceneData = activeSession?.scene ?? null;
  const sceneId = sceneData ? String(sceneData.id) : undefined;
  const roomName = sceneData?.name ?? roomData?.name ?? 'Room';

  // RoomHeader combat/battle badges (#2157) — GamePage is the composition root,
  // so it calls both hooks once here and threads the derived booleans down
  // through FocusPanel -> RoomPanel -> RoomHeader.
  const { data: activeEncounter } = useEncounterForScene(sceneData?.id ?? 0);

  // #3761 — CombatRail's GM tab and outcome-dismiss need the full SceneDetail
  // (viewer_can_gm specifically), which the websocket-derived `sceneData`
  // (a lighter SceneSummary) doesn't carry. Only fetched once an encounter
  // actually exists, mirroring SceneDetailPage.tsx's own plain useQuery shape.
  const { data: combatSceneDetail } = useQuery<SceneDetail>({
    queryKey: ['scene', String(sceneData?.id ?? '')],
    queryFn: () => fetchScene(String(sceneData?.id)),
    enabled: activeEncounter != null && sceneData?.id != null,
  });

  const { data: activeBattle } = useBattleForSceneQuery(sceneData?.id ?? null);
  const hasActiveEncounter = activeEncounter != null;
  const hasActiveBattle = activeBattle != null && activeBattle.outcome === 'unresolved';

  // Final-review Finding I1 — ported from SceneDetailPage.tsx (#3551): the
  // scene's active-encounter poll (useEncounterForScene, 15s interval) drops
  // a completed encounter from its result, which would otherwise unmount
  // CombatRail (and its outcome banner) before the player can see/dismiss
  // it. lingeringEncounterId remembers the last real encounter id and keeps
  // the rail mounted on it until CombatRail's onDismissOutcome fires;
  // dismissedEncounterId hides the rail immediately on dismiss rather than
  // waiting up to 15s for the next poll. Deliberately does NOT feed
  // `hasActiveEncounter` (the banner/nav-icon signal stays the raw "an
  // encounter genuinely exists" boolean) — only the rail itself lingers.
  const [lingeringEncounterId, setLingeringEncounterId] = useState(0);
  const [dismissedEncounterId, setDismissedEncounterId] = useState(0);
  const encounterId = activeEncounter?.id ?? 0;
  const prevSceneIdForEncounterRef = useRef(sceneData?.id ?? 0);
  useEffect(() => {
    const currentSceneId = sceneData?.id ?? 0;
    if (prevSceneIdForEncounterRef.current !== currentSceneId) {
      prevSceneIdForEncounterRef.current = currentSceneId;
      setLingeringEncounterId(encounterId > 0 ? encounterId : 0);
      setDismissedEncounterId(0);
      return;
    }
    if (encounterId > 0) {
      setLingeringEncounterId(encounterId);
    }
  }, [sceneData?.id, encounterId]);
  const railEncounterId = encounterId || lingeringEncounterId;
  const showCombatRail = railEncounterId > 0 && railEncounterId !== dismissedEncounterId;

  // GamePage is the composition root (#2156): it calls the scene-feed +
  // threading hooks once for the active session's scene and feeds both the
  // left column (ThreadSidebar via ConversationSidebar) and the center
  // (SceneMessages + composer). Called unconditionally — sceneId is simply
  // undefined with no active scene, which both hooks handle without firing
  // network calls or producing threads.
  const { allInteractions, hasNextPage, fetchNextPage } = useSceneInteractions(sceneId, active);
  const threadLastSeen = activeSession?.threadLastSeen ?? EMPTY_THREAD_LAST_SEEN;
  const sceneBaselineId = activeSession?.sceneBaselineId ?? null;
  const threading = useThreading(allInteractions, roomName, {
    lastSeenByThread: threadLastSeen,
    viewerPersonaId: personaId,
    sceneBaselineId,
  });

  const openThreadTabs = activeSession?.openThreadTabs ?? EMPTY_OPEN_TABS;
  const activeThreadTabRaw = activeSession?.activeThreadTab ?? null;
  // Guard against a stale active pointer (e.g. hydration races): only an
  // OPEN tab may be active; anything else is the room anchor.
  const activeThreadTab =
    activeThreadTabRaw !== null && openThreadTabs.includes(activeThreadTabRaw)
      ? activeThreadTabRaw
      : null;

  useThreadTabPersistence(active, sceneId, openThreadTabs, activeThreadTabRaw, account?.id);

  // #3761 Task 1: lifted from PlaySidebar/SidebarTabPanel so a later top-bar
  // combat banner (Task 3) can also drive the sidebar into view.
  // `jumpToCombat` (Task 2) is the first real caller of this state — it jumps
  // to Here mode + the Room tab, where `CombatRail` already renders.
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>(
    sceneId && threading ? 'conversations' : 'here'
  );
  const [hereActiveTab, setHereActiveTab] = useState('room');
  const jumpToCombat = useCallback(() => {
    setSidebarMode('here');
    setHereActiveTab('room');
  }, []);

  const [composerMode, setComposerMode] = useState<ComposerMode | undefined>();

  // #2165: the active conversation tab narrows the feed to its thread; the
  // room anchor keeps the existing filtered feed. The composer's audience is
  // DERIVED from the active tab every render (never stored) — that derivation
  // is the mis-send guard.
  const tabInteractions = useMemo(() => {
    if (activeThreadTab === null) return threading.filteredInteractions;
    return threading.interactionsByThread.get(activeThreadTab) ?? [];
  }, [activeThreadTab, threading.filteredInteractions, threading.interactionsByThread]);

  // The label is the truth (#3857): with nothing chosen yet (a fresh connection,
  // or the reset on every character or scene change) the room anchor's mode is
  // Pose, so a typed line is a pose and never a raw command by accident. The
  // default is derived here, never stored, like the tab-locked modes below it.
  const effectiveComposerMode = useMemo(() => {
    if (activeThreadTab === null) {
      return composerMode ?? roomComposerMode(threading.threads, roomName);
    }
    return tabKeyToComposerMode(activeThreadTab, threading.threads, roomName);
  }, [activeThreadTab, threading.threads, roomName, composerMode]);

  const conversationTabs = useMemo<ConversationTabStripProps | undefined>(() => {
    if (!sceneId || !active || openThreadTabs.length === 0) return undefined;
    const roomThread = threading.threads.find((t) => t.key === 'room');
    return {
      roomLabel: roomName,
      roomUnreadCount: roomThread?.unreadCount ?? 0,
      tabs: buildTabDescriptors(openThreadTabs, threading.threads),
      activeKey: activeThreadTab,
      onSelect: (key: string | null) => {
        dispatch(setActiveThreadTab({ character: active, threadKey: key }));
        // #2165 review fix: the strip's room-anchor tab must reset the
        // composer the same way the sidebar's room row does (handleThreadClick
        // below) — otherwise a stale locked mode (e.g. a whisper) survives the
        // switch back to the room anchor.
        if (key === null) {
          setComposerMode(roomComposerMode(threading.threads, roomName));
        }
      },
      onClose: (key: string) => dispatch(closeThreadTab({ character: active, threadKey: key })),
    };
  }, [sceneId, active, openThreadTabs, threading.threads, roomName, activeThreadTab, dispatch]);

  // Character-card drawer (#2156 Task 7): the clicked bubble's persona identity,
  // or null when the drawer is closed. GamePage owns this state (mirrored on
  // SceneDetailPage) since the drawer opens "in place" over whichever surface
  // the avatar was clicked on, not as a route navigation.
  const [cardPersona, setCardPersona] = useState<PoseUnitAvatarClickPersona | null>(null);
  const [replyTarget, setReplyTarget] = useState<Interaction | null>(null);
  const [reference, setReference] = useState<{
    kind: string;
    key: string;
    title: string;
    poseId?: string;
    timestamp?: string;
  } | null>(() => {
    const kind = searchParams.get('referenceKind');
    const key = searchParams.get('referenceKey');
    return kind && key
      ? {
          kind,
          key,
          title: searchParams.get('referenceTitle') ?? key,
          poseId: searchParams.get('referencePose') ?? undefined,
          timestamp: searchParams.get('referenceTimestamp') ?? undefined,
        }
      : null;
  });
  // React Router updates searchParams on browser back/forward. Keep the
  // historical reader synchronized with that URL rather than only its opener.
  useEffect(() => {
    const kind = searchParams.get('referenceKind');
    const key = searchParams.get('referenceKey');
    setReference(
      kind && key
        ? {
            kind,
            key,
            title: searchParams.get('referenceTitle') ?? key,
            poseId: searchParams.get('referencePose') ?? undefined,
            timestamp: searchParams.get('referenceTimestamp') ?? undefined,
          }
        : null
    );
  }, [searchParams]);

  const openReference = useCallback(
    (next: { kind: string; key: string; title: string; poseId?: string; timestamp?: string }) => {
      setReference(next);
      setSearchParams((current) => {
        const params = new URLSearchParams(current);
        params.set('referenceKind', next.kind);
        params.set('referenceKey', next.key);
        if (next.poseId) params.set('referencePose', next.poseId);
        else params.delete('referencePose');
        if (next.timestamp) params.set('referenceTimestamp', next.timestamp);
        else params.delete('referenceTimestamp');
        params.delete('referenceTitle');
        return params;
      });
    },
    [setSearchParams]
  );
  const returnToLive = useCallback(() => {
    setReference(null);
    setSearchParams((current) => {
      const params = new URLSearchParams(current);
      params.delete('referenceKind');
      params.delete('referenceKey');
      params.delete('referencePose');
      params.delete('referenceTimestamp');
      params.delete('referenceTitle');
      return params;
    });
  }, [setSearchParams]);
  const referenceSceneId = reference?.key.startsWith('scene:') ? reference.key.slice(6) : undefined;
  const {
    data: referencePage,
    error: referenceError,
    isPending: referenceLoading,
    refetch: refetchReference,
  } = useQuery<PlayPage<Interaction>>({
    queryKey: [
      'play-reference',
      reference?.kind,
      reference?.key,
      reference?.poseId,
      reference?.timestamp,
    ],
    queryFn: () =>
      reference?.poseId
        ? fetchPlayContext({
            id: reference.poseId,
            scene: referenceSceneId,
            timestamp: reference.timestamp,
            conversation: reference.key,
            from: reference.timestamp
              ? (() => {
                  const start = new Date(reference.timestamp);
                  start.setDate(start.getDate() - 90);
                  return start.toISOString();
                })()
              : undefined,
          }).then((context) => ({
            results: context.results,
            before: context.before,
            after: context.after,
            snapshot: new Date().toISOString(),
          }))
        : fetchPlayPoses({ scene: referenceSceneId, conversation: reference?.key }),
    enabled: Boolean(reference),
  });
  const referenceStatus =
    referenceError instanceof PlayFetchError ? referenceError.status : undefined;
  const referenceUnavailable = referenceStatus === 403 || referenceStatus === 404;
  const referenceRetryable = Boolean(referenceError) && !referenceUnavailable;

  const handleWhisper = useCallback(
    (name: string) => {
      if (active) dispatch(setActiveThreadTab({ character: active, threadKey: null }));
      setComposerMode({ command: 'whisper', targets: [name], label: `Whisper → ${name}` });
      setCardPersona(null);
    },
    [active, dispatch]
  );

  const handleReply = useCallback(
    (interaction: Interaction) => {
      setReplyTarget(interaction);
      if (active) {
        // #3787 rework: a nested exchange opens ONE tab, not one per level --
        // `getThreadKey` already prefers `root_thread_id` for exactly this, so
        // the explicit read ahead of it does too rather than quietly disagreeing.
        const key =
          interaction.root_thread_id ?? interaction.thread_id ?? getThreadKey(interaction);
        if (key !== 'room') dispatch(openThreadTab({ character: active, threadKey: key }));
      }
    },
    [active, dispatch]
  );

  // Keep scene baselines, thread filters, composer state, and read cursors aligned
  // when the active scene or puppet changes.
  useSceneThreadStateSync({
    sceneId,
    active,
    sceneBaselineId: activeSession?.sceneBaselineId,
    allInteractions,
    activeThreadTab,
    resetForNewScene: threading.resetForNewScene,
    setComposerMode,
    setReplyTarget,
    dispatch,
  });

  // #2165: the sidebar is the open-a-tab surface. A conversation row opens or
  // focuses its tab; the room row focuses the anchor. The old
  // toggleThreadVisibility narrowing is retired for the room feed — the
  // per-participant mute (ThreadFilterModal) still applies to the anchor.
  const handleThreadClick = (key: string) => {
    if (!active) return;
    if (key === 'room') {
      dispatch(setActiveThreadTab({ character: active, threadKey: null }));
      const roomThread = threading.threads.find((t) => t.key === 'room');
      if (roomThread) setComposerMode(threadToComposerMode(roomThread, roomName));
      return;
    }
    dispatch(openThreadTab({ character: active, threadKey: key }));
  };

  // #2165 review fix: the sidebar's "All" button must restore the room feed,
  // not just reset the filter/mute state. `threading.showAll` alone clears
  // `enabledThreadKeys`/`hiddenPersonaIds` but leaves an active conversation
  // TAB in place — without also re-anchoring the tab, the tab strip keeps a
  // whisper tab selected and the "All" click appears to do nothing.
  const threadingShowAll = threading.showAll;
  const handleShowAll = useCallback(() => {
    threadingShowAll();
    if (active) dispatch(setActiveThreadTab({ character: active, threadKey: null }));
  }, [threadingShowAll, active, dispatch]);

  // Scene toolset (#2156 Task 6) — GamePage is the composition root, so it
  // owns the same handler state SceneDetailPage.tsx:120-178 owns, mirrored
  // exactly: consent, places, pending action attachments, and the action
  // panel. `PlaceBar`'s `sceneId` prop is actually used as the ROOM id in its
  // `fetchPlaces(?room=)` query (confirmed by reading PlaceBar.tsx +
  // actionQueries.ts) — so /game passes the real room id (`roomData.id`),
  // not the scene id. (`SceneDetailPage` passes the scene id, which is a
  // pre-existing latent bug in the places query on that page — left
  // untouched here; see the task report.)
  const placesRoomId = sceneId && roomData ? String(roomData.id) : undefined;

  // #3810: `placesData` is kept ONLY to resolve a display NAME for the current
  // place (cosmetic, used only in the pre-emptive refusal's hint text). The
  // load-bearing boolean/id come from Redux's room_state push instead of this
  // query's own `viewer_is_present` field, which is never invalidated by
  // anyone's join/leave (confirmed: no caller anywhere calls
  // queryClient.invalidateQueries(['scene-places', ...])) and so goes stale
  // for up to the query's 5-minute staleTime, including for the viewer's OWN
  // moves. `currentPlaceId` below is correct the instant a fresh room_state
  // frame arrives instead.
  const { data: placesData } = useQuery({
    queryKey: ['scene-places', placesRoomId, ...(active ? [active] : [])],
    queryFn: () => fetchPlaces(placesRoomId!),
    enabled: !!placesRoomId,
  });
  // #3760 Task 10 fix: `currentPlaceId` is threaded down to CommandInput so tt
  // (tabletalk) can dispatch via executeAction with a real place kwarg, the
  // same way say/whisper already do.
  const currentPlaceId = roomData?.viewer_place_id ?? null;
  const isAtPlace = currentPlaceId !== null;
  const currentPlaceName =
    placesData?.results?.find((place) => place.id === currentPlaceId)?.name ?? null;

  // Pending unlinked actions for the chip strip — only fetched once a scene
  // is active (personaId gated to null otherwise disables the query).
  const { data: pendingActions } = usePendingUnlinkedActions(
    sceneId ?? '',
    sceneId ? personaId : null
  );
  const pendingActionIds = useMemo(() => pendingActions.map((a) => a.id), [pendingActions]);

  const [detachedActionIds, setDetachedActionIds] = useState<number[]>([]);
  const handleDetach = useCallback((actionId: number) => {
    setDetachedActionIds((prev) => (prev.includes(actionId) ? prev : [...prev, actionId]));
  }, []);
  const handleUndoDetach = useCallback((actionId: number) => {
    setDetachedActionIds((prev) => prev.filter((id) => id !== actionId));
  }, []);
  const handlePoseSubmitted = useCallback(() => {
    setDetachedActionIds([]);
  }, []);

  const [targetToAppend, setPendingTarget] = useState<string | null>(null);
  const [actionAttachment, setActionAttachment] = useState<ActionAttachmentInfo | null>(null);
  const queryClient = useQueryClient();
  const attachedActionsInFlight = useRef(new Set<string>());
  const attachedActionsCompleted = useRef(new Set<string>());

  const handleDismissOutcome = useCallback(() => {
    if (sceneData?.id != null) {
      queryClient.invalidateQueries({ queryKey: combatKeys.encountersForScene(sceneData.id) });
    }
    // Final-review Finding I1: hide the rail immediately (mirrors
    // SceneDetailPage.tsx's handleDismissOutcome) rather than waiting on the
    // next 15s poll to drop it.
    setDismissedEncounterId(railEncounterId);
    setLingeringEncounterId(0);
  }, [queryClient, sceneData?.id, railEncounterId]);

  const submitAction = useMutation({
    mutationFn: ({ action }: { action: ActionAttachmentInfo; clientRequestId: string }) =>
      createActionRequest(sceneId ?? '', {
        action_key: action.actionKey,
        target_persona_id: action.targetPersonaId,
        technique_id: action.techniqueId,
      }),
    onSuccess: (_result, variables) => {
      attachedActionsInFlight.current.delete(variables.clientRequestId);
      attachedActionsCompleted.current.add(variables.clientRequestId);
      setActionAttachment(null);
      // No 'scene-messages' invalidation here (#2156 review fix): nothing in
      // this codebase ever queries that key — the scene feed here is
      // `useSceneInteractions`, which merges the WS-pushed interaction with no
      // React Query cache to invalidate. The stale call was dead on arrival.
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
    },
    onError: (_error, variables) => {
      attachedActionsInFlight.current.delete(variables.clientRequestId);
      // Keep the attachment so the user can retry.
    },
  });

  const handleSubmitAction = useCallback(
    (action: ActionAttachmentInfo, clientRequestId?: string) => {
      const correlationId =
        clientRequestId ?? `${action.actionKey}:${action.targetPersonaId ?? ''}`;
      if (
        attachedActionsInFlight.current.has(correlationId) ||
        attachedActionsCompleted.current.has(correlationId)
      )
        return;
      attachedActionsInFlight.current.add(correlationId);
      submitAction.mutate({ action, clientRequestId: correlationId });
    },
    [submitAction]
  );

  const handleTargetConsumed = useCallback(() => {
    setPendingTarget(null);
  }, []);

  const handleActionAttach = useCallback((action: ActionAttachmentInfo) => {
    setActionAttachment(action);
  }, []);

  const handleActionDetach = useCallback(() => {
    setActionAttachment(null);
  }, []);

  const liveGameWindowHandlers = reference
    ? {
        onAvatarClick: undefined,
        onAddTarget: undefined,
        onAttachAction: undefined,
        onActionAttach: undefined,
        onActionDetach: undefined,
        onSubmitAction: undefined,
        onReply: undefined,
        replyTarget: null,
        conversationTabs: undefined,
      }
    : {
        onAvatarClick: setCardPersona,
        onAddTarget: setPendingTarget,
        onAttachAction: handleActionAttach,
        onActionAttach: handleActionAttach,
        onActionDetach: handleActionDetach,
        onSubmitAction: handleSubmitAction,
        onReply: handleReply,
        replyTarget,
        conversationTabs,
      };

  if (!account) {
    return (
      <div className="mx-auto max-w-sm text-center">
        <p className="mb-4">You must be logged in to access the game.</p>
        <div className="flex justify-center gap-4">
          <Link to="/login" className="text-blue-500 hover:underline">
            Log in
          </Link>
          <Link to="/register" className="text-blue-500 hover:underline">
            Register
          </Link>
        </div>
      </div>
    );
  }

  // The tab label mirrors whatever is currently focused. While focused
  // on the room, fall back to the room name; defaults to "Room" when
  // there's no active session yet.
  const roomTabLabel = deriveRoomTabLabel(focus.current, roomData?.name);
  const displaySceneFeed = reference
    ? sceneFeedProps(referenceSceneId ?? 'history', referencePage?.results ?? [], false, () => {})
    : sceneFeedProps(sceneId, tabInteractions, hasNextPage, fetchNextPage);

  const gameWindowProps: ComponentProps<typeof GameWindow> = {
    characters,
    isStaff: account.is_staff,
    accountId: account.id,
    sceneFeed: displaySceneFeed,
    room: roomData,
    ambientInteractions: activeSession?.ambientInteractions,
    lifecycleState: activeEncounter ? 'encounter' : activeSession?.lifecycleState,
    composerMode: effectiveComposerMode,
    onModeChange: setComposerMode,
    personaId,
    ...liveGameWindowHandlers,
    targetToAppend,
    onTargetConsumed: handleTargetConsumed,
    actionAttachment,
    pendingActionIds,
    detachedActionIds,
    onPoseSubmitted: handlePoseSubmitted,
    onCancelReply: () => setReplyTarget(null),
    draftScopePrefix: `account:${account.id}`,
    roomId: roomData?.id ?? null,
    roomName,
    isAtPlace,
    currentPlaceId,
    currentPlaceName,
    speakingAs: speakingAsProps(activeEntry),
    reference,
    targetPoseId: reference?.poseId,
    onReturnToLive: returnToLive,
    referenceUnavailable: Boolean(reference && referenceUnavailable),
    referenceLoading: Boolean(reference && referenceLoading),
    referenceRetryable: Boolean(reference && referenceRetryable),
    onRetryReference: () => refetchReference(),
    ...placeWidgets(placesRoomId, active, currentPlaceId),
    pendingAttachments: sceneId ? (
      <PendingActionAttachments
        sceneId={sceneId}
        personaId={personaId}
        detachedIds={detachedActionIds}
        onDetach={handleDetach}
        onUndoDetach={handleUndoDetach}
      />
    ) : undefined,
  };

  return (
    <>
      <GameLayout
        accountId={account?.id}
        topBar={
          <GameTopBar
            characters={characters}
            hasActiveEncounter={hasActiveEncounter}
            encounterId={activeEncounter?.id}
            onJumpToCombat={jumpToCombat}
          />
        }
        center={
          <GameCenter
            sceneId={sceneId}
            accountId={account.id}
            activeCharacter={active}
            gameWindow={gameWindowProps}
          />
        }
        sidebar={
          <PlaySidebar
            accountId={account?.id}
            mode={sidebarMode}
            onModeChange={setSidebarMode}
            hasActiveEncounter={hasActiveEncounter}
            onJumpToCombat={jumpToCombat}
            here={
              <GameRightSidebar
                roomTabLabel={roomTabLabel}
                isDreaming={isDreaming}
                activeCharacterId={activeCharacterId}
                active={active}
                focus={focus}
                roomData={roomData}
                sceneData={sceneData}
                hasActiveEncounter={hasActiveEncounter}
                hasActiveBattle={hasActiveBattle}
                showCombatRail={showCombatRail}
                railEncounterId={railEncounterId}
                combatSceneDetail={combatSceneDetail}
                onDismissOutcome={handleDismissOutcome}
                activeTab={hereActiveTab}
                onTabChange={setHereActiveTab}
              />
            }
            threading={sceneId ? threading : undefined}
            onThreadClick={handleThreadClick}
            onShowAll={handleShowAll}
            selectedThreadKey={activeThreadTab ?? 'room'}
            onOpenReference={openReference}
          />
        }
      />
      <CharacterCardDrawer
        persona={cardPersona}
        onClose={() => setCardPersona(null)}
        viewerEntryId={viewerEntryId}
        onWhisper={handleWhisper}
      />
    </>
  );
}
