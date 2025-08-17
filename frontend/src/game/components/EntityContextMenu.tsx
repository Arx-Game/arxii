import type { CommandSpec } from '@/game/types';
import type { MyRosterEntry } from '@/roster/types';
import { QuickAction } from './QuickAction';

interface EntityContextMenuProps {
  character: MyRosterEntry['name'];
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
