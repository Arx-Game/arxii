import { useAppSelector } from '@/store/hooks';
import { QuickAction } from './QuickAction';

export function QuickActions() {
  const { active, sessions } = useAppSelector((state) => state.game);
  if (!active) return null;
  const commands = sessions[active]?.commands ?? [];

  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="mb-2 font-semibold">Quick Actions</h3>
      <div className="flex gap-1">
        {commands.map((cmd) => (
          <QuickAction key={cmd.action} character={active} {...cmd} />
        ))}
      </div>
    </div>
  );
}
