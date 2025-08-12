import { ACTION_ICON_MAP } from '@/game/actions';
import { useGameSocket } from '@/hooks/useGameSocket';

interface CommandSpec {
  action: string;
  command: string;
}

interface EntityContextMenuProps {
  character: string;
  commands: CommandSpec[];
}

export function EntityContextMenu({ character, commands }: EntityContextMenuProps) {
  const { send } = useGameSocket();

  return (
    <div className="flex gap-1">
      {commands.map(({ action, command }) => {
        const Icon = ACTION_ICON_MAP[action];
        if (!Icon) return null;
        return (
          <button
            key={action}
            onClick={() => send(character, command)}
            aria-label={action}
            className="rounded p-1 hover:bg-accent"
          >
            <Icon className="h-4 w-4" />
          </button>
        );
      })}
    </div>
  );
}
