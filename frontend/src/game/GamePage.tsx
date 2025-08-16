import { GameWindow } from './components/GameWindow';
import { CharacterPanel } from './components/CharacterPanel';
import { QuickActions } from './components/QuickActions';
import { useMyRosterEntriesQuery } from '../roster/queries';
import { Toaster } from '../components/ui/sonner';
import { Link } from 'react-router-dom';
import { useAccount } from '../store/hooks';

export function GamePage() {
  const account = useAccount();
  const { data: characters = [] } = useMyRosterEntriesQuery();

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

  return (
    <div className="mx-auto max-w-4xl">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <GameWindow characters={characters} />
        </div>
        <div className="space-y-6">
          <CharacterPanel characters={characters} />
          <QuickActions />
        </div>
      </div>
      <Toaster />
    </div>
  );
}
