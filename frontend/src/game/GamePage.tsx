import { GameWindow } from './components/GameWindow';
import { CharacterPanel } from './components/CharacterPanel';
import { QuickActions } from './components/QuickActions';
import { useMyRosterEntriesQuery } from '../roster/queries';
import { Toaster } from '../components/ui/sonner';

export function GamePage() {
  const { data: characters = [] } = useMyRosterEntriesQuery();
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
