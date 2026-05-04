import { GameLayout } from './components/GameLayout';
import { GameTopBar } from './components/GameTopBar';
import { GameWindow } from './components/GameWindow';
import { ConversationSidebar } from './components/ConversationSidebar';
import { FocusPanel } from './components/FocusPanel';
import { SidebarTabPanel } from './components/SidebarTabPanel';
import { EventsSidebarPanel } from '@/events/components/EventsSidebarPanel';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useFocusStack, type FocusEntry } from '@/inventory/hooks/useFocusStack';
import { Toaster } from '@/components/ui/sonner';
import { Link } from 'react-router-dom';
import { useAccount } from '@/store/hooks';
import { useAppSelector } from '@/store/hooks';

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

  const activeSession = active ? sessions[active] : null;
  const roomData = activeSession?.room ?? null;
  const sceneData = activeSession?.scene ?? null;

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
        leftSidebar={<ConversationSidebar />}
        center={<GameWindow characters={characters} />}
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
            eventsPanel={<EventsSidebarPanel />}
          />
        }
      />
      <Toaster />
    </>
  );
}
