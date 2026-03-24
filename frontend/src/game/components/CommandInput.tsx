import { useState, useCallback } from 'react';
import { useGameSocket } from '@/hooks/useGameSocket';
import { RichTextInput } from '@/components/RichTextInput';
import type { MyRosterEntry } from '@/roster/types';

interface CommandInputProps {
  character: MyRosterEntry['name'];
}

export function CommandInput({ character }: CommandInputProps) {
  const [command, setCommand] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const { send } = useGameSocket();

  const handleSubmit = useCallback(() => {
    const trimmed = command.trim();
    if (trimmed) {
      send(character, trimmed);
      setHistory((prev) => [...prev, trimmed]);
      setHistoryIndex(-1);
      setCommand('');
    }
  }, [character, command, send]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'ArrowUp' && command === '') {
      e.preventDefault();
      if (history.length > 0) {
        const newIndex = historyIndex <= 0 ? history.length - 1 : historyIndex - 1;
        setHistoryIndex(newIndex);
        setCommand(history[newIndex]);
      }
    }
  };

  return (
    <div className="shrink-0 border-t">
      <RichTextInput
        value={command}
        onChange={(val) => {
          setCommand(val);
          setHistoryIndex(-1);
        }}
        onSubmit={handleSubmit}
        onKeyDown={handleKeyDown}
        placeholder="Write a pose..."
        rows={2}
      />
    </div>
  );
}
