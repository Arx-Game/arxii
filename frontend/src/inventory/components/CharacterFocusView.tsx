/**
 * CharacterFocusView — sidebar drill-in for "looking at a character".
 *
 * Renders the character's name, a placeholder slot for a future Status
 * panel (combat follow-up), and the list of currently-visible worn items
 * fetched via ``useVisibleWornItems``. Each worn-item row is a button
 * that delegates to ``onItemClick`` so the parent can push the next
 * focus-stack entry (drill into an item).
 *
 * The character description is not yet fetched here — Phase A's right
 * sidebar already shows the character name from the room state, and
 * pulling a fuller description string is tracked as a follow-up to this
 * task (it requires either a new endpoint or extending the look payload
 * to expose ``CharacterState.get_display_description``).
 */

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { humanizeRegionLayer } from '../humanizeRegionLayer';
import { useVisibleWornItems } from '../hooks/useVisibleWornItems';

interface CharacterFocusViewProps {
  character: { id: number; name: string };
  onItemClick: (item: { id: number; name: string }) => void;
  className?: string;
}

export function CharacterFocusView({ character, onItemClick, className }: CharacterFocusViewProps) {
  const { data: visibleItems = [], isLoading } = useVisibleWornItems(character.id);

  return (
    <div className={cn('flex flex-col gap-4 p-4', className)}>
      <header>
        <h2 className="text-xl font-bold">{character.name}</h2>
      </header>

      {/*
        Status placeholder — populated by the combat roadmap (separate phase).
        Rendered as an empty marker div so the sidebar layout is stable when
        the slot lights up. Hidden + aria-hidden until then.
      */}
      <div data-placeholder="status" className="hidden" aria-hidden="true" />

      <section aria-labelledby="worn-heading">
        <h3
          id="worn-heading"
          className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Wearing
        </h3>

        {isLoading ? (
          <div className="space-y-2" data-testid="visible-worn-loading">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : visibleItems.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">Nothing visible.</p>
        ) : (
          <ul className="space-y-1">
            {visibleItems.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onItemClick({ id: item.id, name: item.display_name })}
                  className="flex w-full items-baseline justify-between gap-2 rounded-md p-2 text-left transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="truncate text-sm">{item.display_name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {humanizeRegionLayer(item.body_region, item.equipment_layer)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
