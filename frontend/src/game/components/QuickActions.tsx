import { useAppSelector } from '@/store/hooks';
import { groupCommands } from '@/game/helpers/commandHelpers';
import { CommandDrawer } from './CommandDrawer';

export function QuickActions() {
  const { active, sessions } = useAppSelector((state) => state.game);
  if (!active) return null;
  const commands = sessions[active]?.commands ?? [];
  const grouped = groupCommands(commands);

  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="mb-2 font-semibold">Quick Actions</h3>
      <div className="flex flex-col gap-4">
        {Object.entries(grouped).map(([category, cmds]) => (
          <div key={category}>
            <h4 className="mb-1 text-sm font-medium">{category}</h4>
            <div className="flex flex-col">
              {cmds.map((cmd, index) => (
                <CommandDrawer
                  key={`${active}-${index}-${cmd.action}`}
                  character={active}
                  {...cmd}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
