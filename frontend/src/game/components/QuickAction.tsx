import { useGameSocket } from '@/hooks/useGameSocket';
import type { CommandSpec } from '@/game/types';
import type { LucideIcon } from 'lucide-react';
import { Eye, Hand, MessageCircle } from 'lucide-react';
import { FormEvent, useState } from 'react';

interface QuickActionProps extends CommandSpec {
  character: string;
}

const ICON_MAP: Record<string, LucideIcon> = {
  look: Eye,
  get: Hand,
  talk: MessageCircle,
};

export function QuickAction({ character, action, params_schema }: QuickActionProps) {
  const { send } = useGameSocket();
  const [fields, setFields] = useState<Record<string, string>>({});

  const Icon = ICON_MAP[action] || Eye;
  const hasParams = Object.keys(params_schema).length > 0;

  const handleChange = (name: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFields({ ...fields, [name]: e.target.value });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const args = Object.keys(params_schema)
      .map((key) => fields[key] ?? '')
      .filter(Boolean)
      .join(' ');
    const cmd = args ? `${action} ${args}` : action;
    send(character, cmd);
    setFields({});
  };

  if (!hasParams) {
    return (
      <button
        onClick={() => send(character, action)}
        aria-label={action}
        className="rounded p-1 hover:bg-accent"
      >
        <Icon className="h-4 w-4" />
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-1">
      {Object.keys(params_schema).map((name) => (
        <input
          key={name}
          aria-label={`${action} ${name}`}
          type="text"
          value={fields[name] ?? ''}
          onChange={handleChange(name)}
          className="w-24 rounded border p-1 text-xs"
        />
      ))}
      <button type="submit" aria-label={action} className="rounded p-1 hover:bg-accent">
        <Icon className="h-4 w-4" />
      </button>
    </form>
  );
}
