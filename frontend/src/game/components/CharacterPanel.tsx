import { useAppDispatch, useAppSelector } from '../../store/hooks';
import { startSession } from '../../store/gameSlice';
import { useGameSocket } from '../../hooks/useGameSocket';
import type { MyRosterEntry } from '../../evennia_replacements/types';

interface CharacterPanelProps {
  characters: MyRosterEntry[];
}

export function CharacterPanel({ characters }: CharacterPanelProps) {
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  const sessions = useAppSelector((state) => state.game.sessions);
  const active = useAppSelector((state) => state.game.active);

  const handleSelect = (name: string) => {
    dispatch(startSession(name));
    if (!sessions[name]?.isConnected) {
      connect(name);
    }
  };

  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="mb-2 font-semibold">Characters</h3>
      {characters.length === 0 ? (
        <p className="text-sm text-muted-foreground">No characters available</p>
      ) : (
        <ul className="space-y-1">
          {characters.map((char) => (
            <li key={char.id}>
              <button
                className={`w-full rounded px-2 py-1 text-left text-sm hover:bg-accent ${
                  active === char.name ? 'bg-accent' : ''
                }`}
                onClick={() => handleSelect(char.name)}
              >
                {char.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
