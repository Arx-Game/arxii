/**
 * TableBeings (#4333 slice 4): the Beings tab of a GM table, for its GM and staff.
 *
 * Staff assign a being to a table (a steward) in admin; this tab is where the
 * table's GM writes that being's pledge types and answers, and answers its
 * closed pledges. Waiting answers come first, then one card per stewarded being.
 */

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useStewardedBeings, useStewardPrompts } from '../beingsQueries';
import type { GMTable, StewardedBeing } from '../types';
import { StewardAnswerPanel, StewardPromptPill } from './StewardAnswerPanel';
import { StewardedBeingEditor } from './StewardedBeingEditor';

function weeksLabel(weeks: number): string {
  return `${weeks} ${weeks === 1 ? 'week' : 'weeks'}`;
}

function BeingCard({ being, onEdit }: { being: StewardedBeing; onEdit: () => void }) {
  const tierCount = being.outcome_tiers.length;
  return (
    <div className="grid gap-2 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <b className="tracking-wide">{being.name}</b>
        <Badge variant="outline">Stewarded by this table</Badge>
      </div>
      {being.description && <p className="text-sm">{being.description}</p>}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {being.favored_resonances.length > 0 && (
          <>
            <span className="text-muted-foreground">Favored resonance:</span>
            <span>{being.favored_resonances.join(', ')}</span>
          </>
        )}
        {being.favored_facets.length > 0 && (
          <>
            <span className="text-muted-foreground">· Favored facet:</span>
            <span>{being.favored_facets.map((facet) => facet.name).join(', ')}</span>
          </>
        )}
        {being.pledges.map((pledge) => (
          <span key={pledge.id} className="flex items-center gap-2">
            <span className="text-muted-foreground">· Pledge:</span>
            <span>{pledge.name}</span>
            <Badge variant="outline">
              favor target {pledge.favor_target} · {weeksLabel(pledge.span_weeks ?? 1)}
            </Badge>
          </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {being.pledges.map((pledge) => {
          const missing = being.outcome_tiers
            .filter((tier) => !pledge.covered_tiers.includes(tier.id))
            .map((tier) => tier.name);
          return (
            <span key={pledge.id}>
              <span className="text-muted-foreground">Answers:</span> {pledge.covered_tiers.length}{' '}
              of {tierCount} outcome tiers written for{' '}
              {being.pledges.length > 1 ? pledge.name : 'this pledge type'}
              {missing.length > 0 ? `; ${missing.join(', ')} not written` : ''}
            </span>
          );
        })}
        <span className="text-muted-foreground">
          · Can be served or invoked by: members of this table
        </span>
        <Button type="button" size="sm" variant="outline" className="ml-auto" onClick={onEdit}>
          Edit {being.name}
        </Button>
      </div>
    </div>
  );
}

export function TableBeings({ table }: { table: GMTable }) {
  const beings = useStewardedBeings(table.id);
  const prompts = useStewardPrompts(table.id);
  const [openPrompt, setOpenPrompt] = useState<number | null>(null);
  const [editing, setEditing] = useState<number | null>(null);

  if (beings.isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  const rows = beings.data?.results ?? [];
  const waiting = prompts.data?.results ?? [];
  const shown = waiting.find((prompt) => prompt.id === openPrompt);
  const editingBeing = rows.find((being) => being.id === editing);

  return (
    <div className="space-y-6">
      {waiting.length > 0 && (
        <section aria-label="GM prompts" className="space-y-2 rounded-md border bg-card p-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            GM prompts
          </h3>
          {waiting.map((prompt) => (
            <StewardPromptPill
              key={prompt.id}
              prompt={prompt}
              onOpen={() => setOpenPrompt(prompt.id)}
            />
          ))}
          {shown && <StewardAnswerPanel key={shown.id} prompt={shown} />}
        </section>
      )}
      {rows.length === 0 && (
        <p className="py-8 text-center text-muted-foreground">This table stewards no beings.</p>
      )}
      {editingBeing ? (
        <section aria-label={`Edit ${editingBeing.name}`} className="space-y-3">
          <h3 className="text-lg font-semibold">{editingBeing.name}</h3>
          <StewardedBeingEditor being={editingBeing} onClose={() => setEditing(null)} />
        </section>
      ) : (
        rows.map((being) => (
          <BeingCard key={being.id} being={being} onEdit={() => setEditing(being.id)} />
        ))
      )}
    </div>
  );
}
