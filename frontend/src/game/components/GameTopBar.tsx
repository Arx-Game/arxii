import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setActiveSession, startSession } from '@/store/gameSlice';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import type { MyRosterEntry } from '@/roster/types';

interface GameTopBarProps {
  characters: MyRosterEntry[];
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export function GameTopBar({ characters }: GameTopBarProps) {
  const dispatch = useAppDispatch();
  const { connect } = useGameSocket();
  const { sessions, active } = useAppSelector((state) => state.game);

  const activeSession = active ? sessions[active] : null;
  const isConnected = activeSession?.isConnected ?? false;

  const handleSelectCharacter = (name: MyRosterEntry['name']) => {
    if (sessions[name]) {
      dispatch(setActiveSession(name));
      if (!sessions[name].isConnected) {
        connect(name);
      }
    } else {
      dispatch(startSession(name));
      connect(name);
    }
  };

  const activeCharacter = characters.find((c) => c.name === active);
  const altCharacters = characters.filter((c) => c.name !== active && sessions[c.name]);
  const unplayedCharacters = characters.filter((c) => c.name !== active && !sessions[c.name]);

  return (
    <div className="flex items-center gap-4 border-b bg-card px-4 py-2">
      <span className="text-sm font-bold tracking-wide text-foreground">ARX II</span>

      <div className="mx-2 h-6 w-px bg-border" />

      {active && activeCharacter ? (
        <div className="flex items-center gap-3">
          <Avatar className="h-9 w-9 ring-2 ring-primary">
            <AvatarImage src={activeCharacter.profile_picture_url ?? undefined} alt={active} />
            <AvatarFallback className="text-xs">{getInitials(active)}</AvatarFallback>
          </Avatar>
          <span className="text-sm font-medium">{active}</span>
        </div>
      ) : null}

      {altCharacters.map((char) => (
        <button
          key={char.id}
          onClick={() => handleSelectCharacter(char.name)}
          className="relative opacity-60 transition-opacity hover:opacity-100"
          title={`Switch to ${char.name}`}
        >
          <Avatar className="h-7 w-7">
            <AvatarImage src={char.profile_picture_url ?? undefined} alt={char.name} />
            <AvatarFallback className="text-xs">{getInitials(char.name)}</AvatarFallback>
          </Avatar>
          {sessions[char.name]?.unread > 0 && (
            <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-red-500" />
          )}
        </button>
      ))}

      {!active &&
        characters.map((char) => (
          <button
            key={char.id}
            onClick={() => handleSelectCharacter(char.name)}
            className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent"
          >
            <Avatar className="h-7 w-7">
              <AvatarImage src={char.profile_picture_url ?? undefined} alt={char.name} />
              <AvatarFallback className="text-xs">{getInitials(char.name)}</AvatarFallback>
            </Avatar>
            <span>{char.name}</span>
          </button>
        ))}

      {active &&
        unplayedCharacters.map((char) => (
          <button
            key={char.id}
            onClick={() => handleSelectCharacter(char.name)}
            className="opacity-40 transition-opacity hover:opacity-80"
            title={`Connect as ${char.name}`}
          >
            <Avatar className="h-6 w-6">
              <AvatarImage src={char.profile_picture_url ?? undefined} alt={char.name} />
              <AvatarFallback className="text-[10px]">{getInitials(char.name)}</AvatarFallback>
            </Avatar>
          </button>
        ))}

      <div className="ml-auto flex items-center gap-2">
        <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
        <span className="text-xs text-muted-foreground">
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
    </div>
  );
}
