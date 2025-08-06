import { useState } from 'react';
import { useGameSocket } from '../../hooks/useGameSocket';
import { Input } from '../../components/ui/input';

export function CommandInput() {
  const [command, setCommand] = useState('');
  const { send } = useGameSocket();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = command.trim();
    if (trimmed) {
      send(trimmed);
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
