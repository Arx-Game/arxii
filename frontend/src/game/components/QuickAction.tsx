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

/**
 * Formats a command using the prompt template and field values.
 * Handles syntax like "@dig room_name=exit_name, back_exit"
 */
function formatCommand(prompt: string, fields: Record<string, string>): string {
  let command = prompt;

  // First, handle optional parameters by checking if they have values
  // Remove optional comma-separated parts if the parameter is empty
  command = command.replace(/, ([a-z_]+)/g, (match, paramName) => {
    const hasValue = fields[paramName] && fields[paramName].trim() !== '';
    if (!hasValue) {
      return ''; // Remove the optional part
    }
    return match; // Keep the optional part
  });

  // Then replace each parameter with its value from fields
  Object.entries(fields).forEach(([key, value]) => {
    if (value && value.trim() !== '') {
      // Use word boundaries to ensure we replace whole parameter names only
      const regex = new RegExp(`\\b${key}\\b`, 'g');
      command = command.replace(regex, value);
    }
  });

  return command;
}

export function QuickAction({ character, action, prompt, params_schema }: QuickActionProps) {
  const { send } = useGameSocket();
  const [fields, setFields] = useState<Record<string, string>>({});

  const Icon = ICON_MAP[action] || Eye;
  const hasParams = Object.keys(params_schema).length > 0;

  const handleChange = (name: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFields({ ...fields, [name]: e.target.value });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const cmd = prompt
      ? formatCommand(prompt, fields)
      : `${action} ${Object.values(fields)
          .filter((v) => v.trim() !== '')
          .join(' ')}`.trim();
    send(character, cmd);
    setFields({});
  };

  if (!hasParams) {
    return (
      <div className="flex items-center gap-2">
        <span className="min-w-16 text-sm font-medium">{action}</span>
        <button
          onClick={() => send(character, action)}
          aria-label={action}
          className="flex items-center gap-1 rounded px-2 py-1 hover:bg-accent"
        >
          <Icon className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <span className="min-w-16 text-sm font-medium">{action}</span>
      <div className="flex items-center gap-1">
        {Object.keys(params_schema).map((name) => (
          <input
            key={name}
            placeholder={name}
            aria-label={`${action} ${name}`}
            type="text"
            value={fields[name] ?? ''}
            onChange={handleChange(name)}
            className="w-24 rounded border p-1 text-xs"
          />
        ))}
        <button
          type="submit"
          aria-label={action}
          className="flex items-center gap-1 rounded px-2 py-1 hover:bg-accent"
        >
          <Icon className="h-4 w-4" />
        </button>
      </div>
    </form>
  );
}
