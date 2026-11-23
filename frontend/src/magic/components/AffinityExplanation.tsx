/**
 * AffinityExplanation (#5293): what each affinity in a character's aura is, in the words
 * staff wrote for it, shown when the reader hovers over or focuses the aura. Creation's
 * Strength step shows the same descriptions; this is where a player reads them again.
 *
 * An affinity with a blank description is left out, and with none to show the aura is
 * drawn bare, exactly as it was before.
 */

import type { ReactNode } from 'react';

import { useAffinities } from '@/character-creation/queries';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';

interface Props {
  /** The affinities the aura holds, largest share first or in any order. */
  names: string[];
  children: ReactNode;
}

export function AffinityExplanation({ names, children }: Props) {
  const { data: affinities = [] } = useAffinities();
  const explained = names
    .map((name) => ({
      name,
      description: affinities.find((affinity) => affinity.name === name)?.description.trim(),
    }))
    .filter((row): row is { name: string; description: string } => Boolean(row.description));

  if (explained.length === 0) return <>{children}</>;

  return (
    <HoverCard openDelay={200}>
      <HoverCardTrigger asChild>
        <div tabIndex={0} className="cursor-help" data-testid="aura-affinity-trigger">
          {children}
        </div>
      </HoverCardTrigger>
      <HoverCardContent className="w-72 space-y-2 text-sm" data-testid="aura-affinity-explanation">
        {explained.map((row) => (
          <div key={row.name}>
            <div className="font-semibold">{row.name}</div>
            <p className="text-muted-foreground">{row.description}</p>
          </div>
        ))}
      </HoverCardContent>
    </HoverCard>
  );
}
