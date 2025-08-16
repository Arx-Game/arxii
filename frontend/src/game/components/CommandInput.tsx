import { useState } from 'react';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Input } from '@/components/ui/input';
import type { MyRosterEntry } from '@/roster/types';

interface CommandInputProps {
  character: MyRosterEntry['name'];
}

export function CommandInput({ character }: CommandInputProps) {
  const [command, setCommand] = useState('');
  const { send } = useGameSocket();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = command.trim();
    if (trimmed) {
      send(character, trimmed);
      setCommand('');
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Input
        type="text"
        placeholder="Enter command..."
        value={command}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCommand(e.target.value)}
      />
    </form>
  );
}
