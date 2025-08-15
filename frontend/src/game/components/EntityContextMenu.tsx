import type { CommandSpec } from '@/game/types';
import { QuickAction } from './QuickAction';

interface EntityContextMenuProps {
  character: string;
  commands: CommandSpec[];
}

export function EntityContextMenu({ character, commands }: EntityContextMenuProps) {
  return (
    <div className="flex gap-1">
      {commands.map((cmd) => (
        <QuickAction key={cmd.action} character={character} {...cmd} />
      ))}
    </div>
  );
}
