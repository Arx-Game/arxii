import { Link } from 'react-router-dom';
import { Card } from './ui/card';

const actions = [
  { to: '/play', label: 'Play' },
  { to: '/roster', label: 'Roster' },
  { to: '/scenes', label: 'Scenes' },
  { to: '/lore', label: 'Lore' },
];

export function QuickActions() {
  return (
    <section className="container mx-auto grid gap-4 py-8 sm:grid-cols-2 md:grid-cols-3">
      {actions.map(({ to, label }) => (
        <Card key={to} className="hover:bg-muted">
          <Link to={to} className="flex h-full w-full items-center justify-center p-6">
            <span className="text-lg font-semibold">{label}</span>
          </Link>
        </Card>
      ))}
    </section>
  );
}
