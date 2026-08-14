/**
 * LanguageSelector (#2993 Task 8) — the composer's "which tongue am I
 * speaking" picker, beside `ModeSelector` in `CommandInput`.
 *
 * Lists the viewer's own active character's known languages
 * (`useMyLanguages`, `/api/species/my-languages/`) and shows the
 * `is_current` row's name as the trigger label, falling back to "Common
 * tongue" when none is current (a null `current_language` speaks the
 * universal default). Selecting an entry sends the WS command string
 * `speak <name>` (bare `speak` to reset to the universal default) through
 * the same `send` path `CommandInput` uses for command submission — there is
 * no REST dispatch for this. `SetLanguageAction`/`CmdSpeak` own the actual
 * mutation server-side; this component just fires the command and refetches.
 */
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown, Languages as LanguagesIcon } from 'lucide-react';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useMyLanguages, speciesKeys } from '@/species/queries';
import { queryClient } from '@/queryClient';
import type { MyRosterEntry } from '@/roster/types';

const UNIVERSAL_LABEL = 'Common tongue';

interface LanguageSelectorProps {
  character: MyRosterEntry['name'];
}

export function LanguageSelector({ character }: LanguageSelectorProps) {
  const { send } = useGameSocket();
  const { data: languages } = useMyLanguages();
  const rows = languages ?? [];
  const currentLabel = rows.find((row) => row.is_current)?.name ?? UNIVERSAL_LABEL;

  const handleSelect = (name: string | null) => {
    send(character, name ? `speak ${name}` : 'speak');
    queryClient.invalidateQueries({ queryKey: speciesKeys.myLanguages() });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          title="Change spoken language"
          className="flex items-center gap-0.5 whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <LanguagesIcon className="h-3 w-3" />
          {currentLabel}
          <ChevronDown className="h-3 w-3" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[10rem]">
        <DropdownMenuItem onSelect={() => handleSelect(null)}>{UNIVERSAL_LABEL}</DropdownMenuItem>
        {rows.map((row) => (
          <DropdownMenuItem key={row.language_id} onSelect={() => handleSelect(row.name)}>
            {row.name}
            <span className="ml-2 text-xs text-muted-foreground">{row.band}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
