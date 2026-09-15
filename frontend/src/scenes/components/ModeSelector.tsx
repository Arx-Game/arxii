import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown, Lock } from 'lucide-react';

interface ModeSelectorProps {
  currentMode: string;
  onModeChange: (mode: string) => void;
  isAtPlace: boolean;
  /**
   * #2165: audience is fixed by the active conversation tab — renders a
   * static label, no dropdown.
   */
  locked?: boolean;
  /** Staff see a Commands entry after a rule (#3857): every line in it goes to the server as typed. */
  staff?: boolean;
}

export const COMMANDS_MODE = 'commands';

const COMMUNICATION_MODES = [
  { key: 'pose', label: 'Pose' },
  { key: 'say', label: 'Say' },
  { key: 'emit', label: 'Emit' },
  { key: 'whisper', label: 'Whisper' },
  // TODO: add shout when CmdShout is implemented
  { key: 'tt', label: 'Tabletalk' },
] as const;

export function ModeSelector({
  currentMode,
  onModeChange,
  isAtPlace,
  locked,
  staff = false,
}: ModeSelectorProps) {
  const currentLabel =
    currentMode === COMMANDS_MODE
      ? 'Commands'
      : (COMMUNICATION_MODES.find((m) => m.key === currentMode)?.label ?? currentMode);

  const visibleModes = isAtPlace
    ? COMMUNICATION_MODES
    : COMMUNICATION_MODES.filter((m) => m.key !== 'tt');

  if (locked) {
    return (
      <span
        title="Audience is locked to this conversation tab"
        className="flex items-center gap-0.5 whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-medium text-muted-foreground"
      >
        <Lock className="h-3 w-3" />
        {currentLabel}
      </span>
    );
  }

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
        {staff && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => onModeChange(COMMANDS_MODE)}>
              Commands
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
