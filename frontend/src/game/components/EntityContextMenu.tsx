import { ACTION_COMPONENT_MAP } from '@/game/actions';
import type { CommandSpec } from '@/game/types';

interface EntityContextMenuProps {
  character: string;
  commands: CommandSpec[];
}

export function EntityContextMenu({ character, commands }: EntityContextMenuProps) {
  return (
    <div className="flex gap-1">
      {commands.map(({ action, command }) => {
        const Component = ACTION_COMPONENT_MAP[action];
        if (!Component) return null;
        return <Component key={action} character={character} action={action} command={command} />;
      })}
    </div>
  );
}
