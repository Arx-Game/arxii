import { useState, useCallback, useEffect } from 'react';
import { useGameSocket } from '@/hooks/useGameSocket';
import { RichTextInput } from '@/components/RichTextInput';
import type { MyRosterEntry } from '@/roster/types';

export interface ComposerMode {
  command: string; // "pose" | "say" | "tt" | "whisper"
  targets: string[]; // persona names for @targeting
  label: string; // "Pose → The Grand Ballroom"
}

const KNOWN_COMMANDS = ['pose', 'say', 'whisper', 'tt', 'tabletalk', 'emote'];

interface CommandInputProps {
  character: MyRosterEntry['name'];
  composerMode?: ComposerMode;
  pendingTarget?: string | null;
  onPendingTargetConsumed?: () => void;
}

export function CommandInput({
  character,
  composerMode,
  pendingTarget,
  onPendingTargetConsumed,
}: CommandInputProps) {
  const [command, setCommand] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const { send } = useGameSocket();

  const handleSubmit = useCallback(() => {
    const trimmed = command.trim();
    if (!trimmed) return;

    let fullCommand = trimmed;
    if (composerMode) {
      const firstWord = trimmed.split(' ')[0].toLowerCase();
      const hasExplicitCommand = KNOWN_COMMANDS.includes(firstWord);

      if (!hasExplicitCommand) {
        const targetStr =
          composerMode.targets.length > 0 ? ` @${composerMode.targets.join(',@')} ` : ' ';
        fullCommand = `${composerMode.command}${targetStr}${trimmed}`;
      }
    }

    send(character, fullCommand);
    setHistory((prev) => [...prev, trimmed]);
    setHistoryIndex(-1);
    setCommand('');
  }, [character, command, composerMode, send]);

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

  // Append @name when a pending target arrives
  useEffect(() => {
    if (pendingTarget) {
      setCommand((prev) => {
        const prefix = prev.trim() ? prev + ' ' : '';
        return `${prefix}@${pendingTarget}`;
      });
      onPendingTargetConsumed?.();
    }
  }, [pendingTarget, onPendingTargetConsumed]);

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
        modeLabel={composerMode?.label}
      />
    </div>
  );
}
