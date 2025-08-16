import { useState } from 'react';
import { useGameSocket } from '@/hooks/useGameSocket';
import { Input } from '@/components/ui/input';
import type { MyRosterEntry } from '@/roster/types';

interface CommandInputProps {
  character: MyRosterEntry['name'];
}

export function CommandInput({ character }: CommandInputProps) {
  const [command, setCommand] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const { send } = useGameSocket();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = command.trim();
    if (trimmed) {
      send(character, trimmed);
      setHistory((prev) => [...prev, trimmed]);
      setHistoryIndex(-1);
      setCommand('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (history.length > 0) {
        const newIndex = historyIndex <= 0 ? history.length - 1 : historyIndex - 1;
        setHistoryIndex(newIndex);
        setCommand(history[newIndex]);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (history.length > 0) {
        const newIndex = historyIndex >= history.length - 1 ? -1 : historyIndex + 1;
        setHistoryIndex(newIndex);
        setCommand(newIndex === -1 ? '' : history[newIndex]);
      }
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Input
        type="text"
        placeholder="Enter command..."
        value={command}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCommand(e.target.value)}
        onKeyDown={handleKeyDown}
      />
    </form>
  );
}
