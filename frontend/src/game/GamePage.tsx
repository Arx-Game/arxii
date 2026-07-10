import { useMemo, useState } from 'react';
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
import { useAppSelector } from '@/store/hooks';
import { useSceneInteractions } from '@/scenes/hooks/useSceneInteractions';
import { useThreading } from '@/scenes/hooks/useThreading';
import { threadToComposerMode } from '@/scenes/hooks/threadToComposerMode';
import type { ComposerMode } from './components/CommandInput';

const DEFAULT_ROOM_ENTRY: FocusEntry = {
  kind: 'room',
  room: null,
  sceneSummary: null,
};

export function GamePage() {
  const account = useAccount();
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
  const threading = useThreading(allInteractions, roomName);
  const [composerMode, setComposerMode] = useState<ComposerMode | undefined>();

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
