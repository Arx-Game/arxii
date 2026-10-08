import * as React from 'react';
import { Command } from 'cmdk';
import { Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useCreateFacet, useNearFacets } from '@/character-creation/queries';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { cn } from '@/lib/utils';
import { facetKey } from '../facetKey';

/**
 * The one way to pick a facet (#4197): the deity page, item crafting and anything else
 * that binds from the flat vocabulary. Type to search what exists; a spelling that
 * resolves nowhere shows what it is near before anything is made, and staff may then
 * create it in the same gesture. Players never create: the vocabulary is authored.
 */
/** What a picker needs of a facet: the editor's refs and the API's rows both fit. */
export interface FacetRef {
  id: number;
  name: string;
}

interface FacetPickerProps {
  /** The vocabulary already loaded by the caller. */
  facets: FacetRef[] | undefined;
  /** Facets already bound here, left out of the list. */
  exclude?: number[];
  onPick: (facet: FacetRef) => void;
  /** Staff only: offer to create a spelling that resolves to no facet. */
  canCreate?: boolean;
  /** The closed button's word. */
  label?: string;
  className?: string;
}

const MIN_QUERY = 2;
const ITEM_CLASS = cn(
  'relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5',
  'text-sm outline-none data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground'
);

export function FacetPicker({
  facets,
  exclude = [],
  onPick,
  canCreate = false,
  label = 'Add facet',
  className,
}: FacetPickerProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const trimmed = query.trim();
  const settled = useDebouncedValue(trimmed, 250);
  const key = facetKey(trimmed);
  const items = React.useMemo(
    () => (facets ?? []).filter((facet) => !exclude.includes(facet.id)),
    [facets, exclude]
  );
  const exact = items.find((facet) => facetKey(facet.name) === key);
  const asking = trimmed.length >= MIN_QUERY && !exact && settled === trimmed;
  const near = useNearFacets(settled, asking);
  const create = useCreateFacet();

  const nearItems = (near.data ?? []).filter((facet) => !exclude.includes(facet.id));
  const nearHasKey = nearItems.some((facet) => facetKey(facet.name) === key);
  const offerCreate = canCreate && asking && !near.isPending && !nearHasKey;

  const choose = (facet: FacetRef) => {
    onPick(facet);
    setQuery('');
    setOpen(false);
  };

  const createNow = () => {
    create.mutate(trimmed, { onSuccess: (facet: FacetRef) => choose(facet) });
  };

  if (!open) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className={className}
        onClick={() => setOpen(true)}
      >
        + {label}
      </Button>
    );
  }

  return (
    <Popover
      open
      onOpenChange={(next) => {
        if (!next) {
          setOpen(false);
          setQuery('');
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" className={className}>
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        <Command loop shouldFilter>
          <Command.Input
            autoFocus
            value={query}
            onValueChange={setQuery}
            placeholder={label}
            aria-label={label}
            className={cn(
              'flex h-9 w-full rounded-md bg-transparent px-3 py-2 text-sm',
              'outline-none placeholder:text-muted-foreground'
            )}
          />
          <Command.List className="max-h-[300px] overflow-y-auto overflow-x-hidden p-1">
            {items.map((facet) => (
              <Command.Item
                key={facet.id}
                value={facet.name}
                keywords={[facet.name]}
                onSelect={() => choose(facet)}
                className={ITEM_CLASS}
              >
                {facet.name}
              </Command.Item>
            ))}
            {asking && nearItems.length > 0 && (
              <Command.Group heading="Did you mean" forceMount>
                {nearItems.map((facet) => (
                  <Command.Item
                    key={`near-${facet.id}`}
                    value={`near:${facet.name}`}
                    forceMount
                    onSelect={() => choose(facet)}
                    className={ITEM_CLASS}
                  >
                    {facet.name}
                  </Command.Item>
                ))}
              </Command.Group>
            )}
            {offerCreate && (
              <Command.Item
                value={`create:${trimmed}`}
                forceMount
                disabled={create.isPending}
                onSelect={createNow}
                className={ITEM_CLASS}
              >
                <Plus className="mr-2 h-4 w-4 shrink-0" aria-hidden="true" />
                {`Create “${trimmed}”`}
              </Command.Item>
            )}
            {!asking && items.length === 0 && (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Nothing to pick yet.
              </div>
            )}
          </Command.List>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
