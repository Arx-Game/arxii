import { ChatWindow } from './ChatWindow';
import { CommandInput } from './CommandInput';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setActiveSession } from '@/store/gameSlice';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Link } from 'react-router-dom';
import type { MyRosterEntry } from '@/roster/types';

interface GameWindowProps {
  characters: MyRosterEntry[];
}

export function GameWindow({ characters }: GameWindowProps) {
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  const { sessions, active } = useAppSelector((state) => state.game);

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

  if (!active) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <p className="text-sm text-muted-foreground">Select a character to begin.</p>
      </div>
    );
  }

  const session = sessions[active];
  const sessionNames = Object.keys(sessions);

  const handleTabClick = (name: MyRosterEntry['name']) => {
    dispatch(setActiveSession(name));
    if (!sessions[name].isConnected) {
      connect(name);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {sessionNames.length >= 2 && (
        <div className="mb-2 flex gap-2 border-b">
          {sessionNames.map((name) => (
            <button
              key={name}
              onClick={() => handleTabClick(name)}
              className={`relative rounded-t px-2 py-1 text-sm ${
                active === name ? 'border-b-2 border-primary' : ''
              }`}
            >
              {name}
              {sessions[name].unread > 0 && (
                <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-red-500" />
              )}
            </button>
          ))}
        </div>
      )}
      <ChatWindow messages={session.messages} isConnected={session.isConnected} />
      <CommandInput character={active} />
    </div>
  );
}
