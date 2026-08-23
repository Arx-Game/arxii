/**
 * CompanionSelector (#3294) — the composer's "pose as my companion" toggle,
 * beside `LanguageSelector`/`ModeSelector` in `CommandInput`.
 *
 * Lists the viewer's own active character's bonded companions that are
 * currently present in the room (`useMyCompanions`, `is_present`), pattern
 * mirroring `LanguageSelector`. Renders nothing when no companion is present
 * (#3294 Decision 4 — never offer a ghost-pose option). Unlike
 * `LanguageSelector`, this doesn't fire a command immediately: selecting a
 * companion is a *controlled* toggle (`value`/`onChange`) — the composer
 * routes the next submitted pose through `POST .../emote/` for that
 * companion instead of a normal pose, until cleared back to "Speak as
 * yourself".
 */
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown, PawPrint } from 'lucide-react';
import { useMyCompanions } from '@/companions/queries';
import type { CompanionSummary } from '@/companions/types';

const SELF_LABEL = 'Speak as yourself';

interface CompanionSelectorProps {
  value: CompanionSummary | null;
  onChange: (companion: CompanionSummary | null) => void;
}

export function CompanionSelector({ value, onChange }: CompanionSelectorProps) {
  const { data: companions } = useMyCompanions();
  const present = (companions ?? []).filter((c) => c.is_present);

  if (present.length === 0) {
    return null;
  }

  const currentLabel = value ? `as ${value.name}` : SELF_LABEL;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          title="Pose as a bonded companion"
          data-testid="companion-selector-trigger"
          className={`flex items-center gap-0.5 whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-medium hover:bg-accent hover:text-accent-foreground ${
            value ? 'text-amber-500' : 'text-muted-foreground'
          }`}
        >
          <PawPrint className="h-3 w-3" />
          {currentLabel}
          <ChevronDown className="h-3 w-3" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[10rem]">
        <DropdownMenuItem onSelect={() => onChange(null)}>{SELF_LABEL}</DropdownMenuItem>
        {present.map((companion) => (
          <DropdownMenuItem key={companion.id} onSelect={() => onChange(companion)}>
            {companion.name}
            <span className="ml-2 text-xs text-muted-foreground">{companion.archetype.name}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
