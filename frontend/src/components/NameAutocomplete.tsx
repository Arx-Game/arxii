import { cn } from '@/lib/utils';

interface NameAutocompleteProps {
  characters: Array<{ name: string; thumbnail_url?: string | null }>;
  query: string;
  visible: boolean;
  onSelect: (name: string) => void;
  onDismiss: () => void;
  selectedIndex: number;
}

export function NameAutocomplete({
  characters,
  query,
  visible,
  onSelect,
  onDismiss: _onDismiss,
  selectedIndex,
}: NameAutocompleteProps) {
  if (!visible) return null;

  const filtered = characters.filter((c) => c.name.toLowerCase().startsWith(query.toLowerCase()));

  if (filtered.length === 0) return null;

  return (
    <div
      className="absolute bottom-full left-0 z-50 mb-1 max-h-48 w-64 overflow-y-auto rounded-md border bg-popover p-1 shadow-md"
      role="listbox"
    >
      {filtered.map((character, index) => (
        <button
          key={character.name}
          type="button"
          role="option"
          aria-selected={index === selectedIndex}
          className={cn(
            'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm',
            index === selectedIndex
              ? 'bg-accent text-accent-foreground'
              : 'hover:bg-accent hover:text-accent-foreground'
          )}
          onMouseDown={(e) => {
            e.preventDefault();
            onSelect(character.name);
          }}
        >
          {character.thumbnail_url && (
            <img
              src={character.thumbnail_url}
              alt=""
              className="h-5 w-5 shrink-0 rounded-full object-cover"
            />
          )}
          <span>{character.name}</span>
        </button>
      ))}
    </div>
  );
}
