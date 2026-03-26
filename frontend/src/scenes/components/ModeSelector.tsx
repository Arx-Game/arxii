import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown } from 'lucide-react';

interface ModeSelectorProps {
  currentMode: string;
  onModeChange: (mode: string) => void;
  isAtPlace: boolean;
}

const COMMUNICATION_MODES = [
  { key: 'pose', label: 'Pose' },
  { key: 'say', label: 'Say' },
  { key: 'emote', label: 'Emit' },
  { key: 'whisper', label: 'Whisper' },
  // TODO: add shout when CmdShout is implemented
  { key: 'tt', label: 'Tabletalk' },
] as const;

export function ModeSelector({ currentMode, onModeChange, isAtPlace }: ModeSelectorProps) {
  const currentLabel = COMMUNICATION_MODES.find((m) => m.key === currentMode)?.label ?? currentMode;

  const visibleModes = isAtPlace
    ? COMMUNICATION_MODES
    : COMMUNICATION_MODES.filter((m) => m.key !== 'tt');

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-0.5 whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <ChevronDown className="h-3 w-3" />
          {currentLabel}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[8rem]">
        {visibleModes.map((mode) => (
          <DropdownMenuItem key={mode.key} onSelect={() => onModeChange(mode.key)}>
            {mode.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
