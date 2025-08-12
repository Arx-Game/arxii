import { useAppSelector } from '@/store/hooks';
import { ACTION_COMPONENT_MAP } from '@/game/actions';

export function QuickActions() {
  const { active, sessions } = useAppSelector((state) => state.game);
  if (!active) return null;
  const commands = sessions[active]?.commands ?? [];

  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="mb-2 font-semibold">Quick Actions</h3>
      <div className="flex gap-1">
        {commands.map(({ action, command }) => {
          const Component = ACTION_COMPONENT_MAP[action];
          if (!Component) return null;
          return <Component key={action} character={active} action={action} command={command} />;
        })}
      </div>
    </div>
  );
}
