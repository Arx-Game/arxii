import { GameLayout } from './components/GameLayout';
import { GameTopBar } from './components/GameTopBar';
import { GameWindow } from './components/GameWindow';
import { ConversationSidebar } from './components/ConversationSidebar';
import { RoomPanel } from './components/RoomPanel';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { Toaster } from '@/components/ui/sonner';
import { Link } from 'react-router-dom';
import { useAccount } from '@/store/hooks';
import { useAppSelector } from '@/store/hooks';

export function GamePage() {
  const account = useAccount();
  const { data: characters = [] } = useMyRosterEntriesQuery();
  const { sessions, active } = useAppSelector((state) => state.game);

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

  return (
    <>
      <GameLayout
        topBar={<GameTopBar characters={characters} />}
        leftSidebar={<ConversationSidebar />}
        center={<GameWindow characters={characters} />}
        rightSidebar={
          <RoomPanel
            character={active}
            room={activeSession?.room ?? null}
            scene={activeSession?.scene ?? null}
          />
        }
      />
      <Toaster />
    </>
  );
}
