import { useEffect, useMemo, useRef, useState } from 'react';
import { GameLayout } from './components/GameLayout';
import { GameTopBar } from './components/GameTopBar';
import { GameWindow } from './components/GameWindow';
import { ConversationSidebar } from './components/ConversationSidebar';
import { FocusPanel } from './components/FocusPanel';
import { SidebarTabPanel } from './components/SidebarTabPanel';
import { PresencePanel } from './components/PresencePanel';
import { EventsSidebarPanel } from '@/events/components/EventsSidebarPanel';
import { StoryTray } from '@/missions/components/StoryTray';
import { StatusPanel } from '@/status/components/StatusPanel';
import { InventorySidebarPanel } from '@/inventory/components/InventorySidebarPanel';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useFocusStack, type FocusEntry } from '@/inventory/hooks/useFocusStack';
import { Toaster } from '@/components/ui/sonner';
import { Link } from 'react-router-dom';
import { useAccount } from '@/store/hooks';
import { useAppSelector, useAppDispatch } from '@/store/hooks';
import { markThreadSeen, setSceneBaseline } from '@/store/gameSlice';
import { useSceneInteractions } from '@/scenes/hooks/useSceneInteractions';
import { useThreading, getThreadKey } from '@/scenes/hooks/useThreading';
import { threadToComposerMode } from '@/scenes/hooks/threadToComposerMode';
import type { ComposerMode } from './components/CommandInput';

const DEFAULT_ROOM_ENTRY: FocusEntry = {
  kind: 'room',
  room: null,
  sceneSummary: null,
};

// Stable empty-object reference so `useThreading`'s memo doesn't see a "changed"
// lastSeenByThread on every render when there's no active session yet (#2156).
const EMPTY_THREAD_LAST_SEEN: Record<string, number> = {};

export function GamePage() {
  const account = useAccount();
  const dispatch = useAppDispatch();
  const { data: characters = [] } = useMyRosterEntriesQuery();
  const { sessions, active } = useAppSelector((state) => state.game);

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
  const personaId = activeEntry?.primary_persona_id ?? null;

  const activeSession = active ? sessions[active] : null;
  const roomData = activeSession?.room ?? null;
  const sceneData = activeSession?.scene ?? null;
  const sceneId = sceneData ? String(sceneData.id) : undefined;
  const roomName = sceneData?.name ?? roomData?.name ?? 'Room';

  // GamePage is the composition root (#2156): it calls the scene-feed +
  // threading hooks once for the active session's scene and feeds both the
  // left column (ThreadSidebar via ConversationSidebar) and the center
  // (SceneMessages + composer). Called unconditionally — sceneId is simply
  // undefined with no active scene, which both hooks handle without firing
  // network calls or producing threads.
  const { allInteractions, hasNextPage, fetchNextPage } = useSceneInteractions(sceneId);
  const threadLastSeen = activeSession?.threadLastSeen ?? EMPTY_THREAD_LAST_SEEN;
  const sceneBaselineId = activeSession?.sceneBaselineId ?? null;
  const threading = useThreading(allInteractions, roomName, {
    lastSeenByThread: threadLastSeen,
    viewerPersonaId: personaId,
    sceneBaselineId,
  });
  const [composerMode, setComposerMode] = useState<ComposerMode | undefined>();

  // Scene-load baseline (#2156 review fix): a single scalar snapshot, not a
  // per-thread-key one. The old per-key baseline one-shotted per KEY, so a
  // brand-new thread appearing mid-session (e.g. a first whisper) got its own
  // key baselined to its first message's id the moment it was observed —
  // countUnread's strict `>` then suppressed the badge on that very first
  // message. Instead: the first time this effect runs for a given `sceneId`,
  // capture the highest interaction id present at that moment as
  // `sceneBaselineId` and never touch it again for this scene.
  // `useThreading`'s `countUnread` falls back to this scalar only for thread
  // keys with no `threadLastSeen` entry, so pre-existing threads (which get a
  // `threadLastSeen` entry from the selected-thread effect below, or already
  // had one) stay zeroed while a genuinely new thread badges from message one.
  // `maxId ?? 0` (not `?? null`, review fix 2): a scene with ZERO interactions
  // at load must still baseline to a real number — interaction ids are DB pks
  // and never 0, so 0 is a safe "baselined empty" sentinel. `null` would be
  // indistinguishable from "baseline effect hasn't run yet", which would make
  // `countUnread` fall through to its no-baseline branch and stay silently
  // unbadged for that scene's first message.
  const sceneBaselinedRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!sceneId || !active) return;
    if (sceneBaselinedRef.current === sceneId) return;
    sceneBaselinedRef.current = sceneId;
    let maxId: number | undefined;
    for (const interaction of allInteractions) {
      const id = Number(interaction.id);
      if (maxId === undefined || id > maxId) maxId = id;
    }
    dispatch(setSceneBaseline({ character: active, baselineId: maxId ?? 0 }));
  }, [sceneId, active, allInteractions, dispatch]);

  // Continuously mark the SELECTED thread seen as its interactions grow — this is
  // the thread the player is actively viewing, so it never accumulates unread.
  // Unselected threads are left alone and accumulate unread from the baseline above.
  useEffect(() => {
    if (!sceneId || !active) return;
    const selectedKey = threading.selectedThreadKey;
    let maxId: number | undefined;
    for (const interaction of allInteractions) {
      if (getThreadKey(interaction) !== selectedKey) continue;
      const id = Number(interaction.id);
      if (maxId === undefined || id > maxId) maxId = id;
    }
    if (maxId !== undefined) {
      dispatch(markThreadSeen({ character: active, threadKey: selectedKey, interactionId: maxId }));
    }
  }, [sceneId, active, allInteractions, threading.selectedThreadKey, dispatch]);

  // Mirrors SceneInteractionPanel's handleThreadClick (#2156 review fix): a
  // thread click toggles that thread's inclusion in the enabled-thread set
  // (which is what useThreading.filteredInteractions actually narrows on),
  // not just the "selected" highlight — otherwise the feed never changes.
  const handleThreadClick = (key: string) => {
    threading.toggleThreadVisibility(key);
    const thread = threading.threads.find((t) => t.key === key);
    if (thread) {
      setComposerMode(threadToComposerMode(thread, roomName));
    }
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
  let roomTabLabel = 'Room';
  switch (focus.current.kind) {
    case 'room':
      roomTabLabel = focus.current.room?.name ?? roomData?.name ?? 'Room';
      break;
    case 'character':
      roomTabLabel = focus.current.character.name;
      break;
    case 'item':
      roomTabLabel = focus.current.item.name;
      break;
  }

  return (
    <>
      <GameLayout
        topBar={<GameTopBar characters={characters} />}
        leftSidebar={
          <ConversationSidebar
            threading={sceneId ? threading : undefined}
            onThreadClick={handleThreadClick}
          />
        }
        center={
          <GameWindow
            characters={characters}
            sceneFeed={
              sceneId
                ? {
                    sceneId,
                    interactions: threading.filteredInteractions,
                    hasNextPage,
                    fetchNextPage,
                  }
                : undefined
            }
            composerMode={composerMode}
            onModeChange={setComposerMode}
            personaId={personaId}
          />
        }
        rightSidebar={
          <SidebarTabPanel
            roomTabLabel={roomTabLabel}
            roomPanel={
              <FocusPanel
                focus={focus}
                roomCharacter={active}
                roomData={roomData}
                sceneData={sceneData}
              />
            }
            storiesPanel={<StoryTray roomKey={roomData?.name ?? 'nowhere'} />}
            eventsPanel={<EventsSidebarPanel />}
            presencePanel={<PresencePanel />}
            statusPanel={
              activeCharacterId ? (
                <StatusPanel characterId={activeCharacterId} characterName={active ?? undefined} />
              ) : undefined
            }
            inventoryPanel={
              activeCharacterId ? (
                <InventorySidebarPanel characterId={activeCharacterId} />
              ) : undefined
            }
          />
        }
      />
      <Toaster />
    </>
  );
}
