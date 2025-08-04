import { GameWindow } from './components/GameWindow';
import { CharacterPanel } from './components/CharacterPanel';
import { QuickActions } from './components/QuickActions';

export function GamePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <GameWindow />
        </div>
        <div className="space-y-6">
          <CharacterPanel />
          <QuickActions />
        </div>
      </div>
    </div>
  );
}
