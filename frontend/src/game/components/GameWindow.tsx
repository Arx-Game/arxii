import { ChatWindow } from './ChatWindow';
import { CommandInput } from './CommandInput';
import { Card, CardContent } from '@/components/ui/card';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setActiveSession } from '@/store/gameSlice';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Link } from 'react-router-dom';
import type { MyRosterEntry } from '@/roster/types';
import { SceneWindow } from './SceneWindow';
import { LocationWindow } from './LocationWindow';

interface GameWindowProps {
  characters: MyRosterEntry[];
}

export function GameWindow({ characters }: GameWindowProps) {
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  const { sessions, active } = useAppSelector((state) => state.game);

  if (characters.length === 0) {
    return (
      <Card className="w-full max-w-[calc(88ch+2rem)]">
        <CardContent className="p-4">
          <p className="text-sm">
            You have no active characters. Visit the{' '}
            <Link to="/roster" className="underline">
              roster
            </Link>{' '}
            to apply for one.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!active) {
    return (
      <Card className="w-full max-w-[calc(88ch+2rem)]">
        <CardContent className="p-4">
          <p className="text-sm text-muted-foreground">Select a character to begin.</p>
        </CardContent>
      </Card>
    );
  }

  const session = sessions[active];

  const handleTabClick = (name: MyRosterEntry['name']) => {
    dispatch(setActiveSession(name));
    if (!sessions[name].isConnected) {
      connect(name);
    }
  };

  return (
    <Card className="w-full max-w-[calc(88ch+2rem)]">
      <CardContent className="p-4">
        <div className="mb-4 flex gap-2 border-b">
          {Object.keys(sessions).map((name) => (
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
        <LocationWindow character={active} room={session.room} />
        <SceneWindow
          character={active}
          scene={session.scene}
          room={session.room ? { id: session.room.id, name: session.room.name } : null}
        />
        <ChatWindow messages={session.messages} isConnected={session.isConnected} />
        <CommandInput character={active} />
      </CardContent>
    </Card>
  );
}
