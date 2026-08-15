/**
 * GrandeurPanel — spend on a once-in-a-lifetime event's grandeur budget (#2357).
 *
 * Venue/entertainment/favors/decor — the uncovered slices of a wedding or
 * coronation budget (food is `EventCatering`'s lane, no panel for it yet —
 * catering is telnet/admin-only today). Mutation goes through the generic
 * action-dispatch endpoint (`ContributeGrandeurAction` / `event_invest_grandeur`),
 * the same seam `TreasuryPanel` uses (Decision 8, #2992) — mirrors its
 * hook/mutation + queries.ts invalidation pattern.
 *
 * Purse-sourced only for now: a treasury-sourced spend is reachable via
 * `event grandeur <id> category=... amount=... org=<name>` in telnet, but the
 * web panel has no "my organizations" picker to build against yet — the server
 * still enforces `can_spend_treasury` either way, so nothing here is unsafe to
 * extend later, just not wired to a UI control yet.
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { formatCoppers } from '@/lib/currency';
import { contributeGrandeur } from '../queries';
import { GRANDEUR_CATEGORIES } from '../types';
import type { EventGrandeurContribution, GrandeurCategory } from '../types';

export interface GrandeurPanelProps {
  eventId: number;
  contributions: EventGrandeurContribution[];
  totalSpent: number;
  /** ObjectDB pk of the viewer's active character; null if none puppeted. */
  actorCharacterId: number | null;
  /** Only DRAFT/SCHEDULED/ACTIVE events can take new contributions. */
  canContribute: boolean;
}

function parsePositiveAmount(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const amount = Number.parseInt(trimmed, 10);
  return amount > 0 ? amount : null;
}

export function GrandeurPanel({
  eventId,
  contributions,
  totalSpent,
  actorCharacterId,
  canContribute,
}: GrandeurPanelProps) {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<GrandeurCategory>('venue');
  const [amountText, setAmountText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const contribute = useMutation({
    mutationFn: (amount: number) =>
      contributeGrandeur(actorCharacterId ?? 0, eventId, category, amount),
    onSuccess: () => {
      setAmountText('');
      queryClient.invalidateQueries({ queryKey: ['event', String(eventId)] }).catch(() => {});
    },
    onError: (err: Error) => setError(err.message),
  });

  if (!canContribute && contributions.length === 0) return null;

  const amount = parsePositiveAmount(amountText);
  const canAct = amount !== null && actorCharacterId !== null && !contribute.isPending;

  function handleContribute() {
    if (amount === null || actorCharacterId === null) return;
    setError(null);
    contribute.mutate(amount);
  }

  return (
    <Card data-testid="grandeur-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Grandeur</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground" data-testid="grandeur-total">
          Total invested: {formatCoppers(totalSpent)}
        </p>

        {contributions.length > 0 && (
          <ul className="space-y-1 text-sm">
            {contributions.map((row) => (
              <li key={row.id} className="flex justify-between gap-2">
                <span>
                  {row.contributed_by_name || '(unknown)'} —{' '}
                  {GRANDEUR_CATEGORIES.find((c) => c.value === row.category)?.label ?? row.category}
                </span>
                <span className="text-muted-foreground">{formatCoppers(row.amount_spent)}</span>
              </li>
            ))}
          </ul>
        )}

        {canContribute && (
          <div className="flex flex-wrap items-center gap-2">
            <Select value={category} onValueChange={(v) => setCategory(v as GrandeurCategory)}>
              <SelectTrigger
                id={`grandeur-category-${eventId}`}
                data-testid="grandeur-category-select"
                className="h-8 w-40 text-sm"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GRANDEUR_CATEGORIES.map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <label htmlFor={`grandeur-amount-${eventId}`} className="sr-only">
              Amount in coppers
            </label>
            <Input
              id={`grandeur-amount-${eventId}`}
              data-testid="grandeur-amount-input"
              inputMode="numeric"
              value={amountText}
              onChange={(e) => setAmountText(e.target.value)}
              placeholder="Amount in coppers"
              className="h-8 w-40 text-sm"
            />
            <Button
              size="sm"
              onClick={handleContribute}
              disabled={!canAct}
              data-testid="grandeur-contribute-button"
            >
              {contribute.isPending ? 'Investing…' : 'Invest'}
            </Button>
          </div>
        )}
        {error && (
          <p className="text-sm text-destructive" data-testid="grandeur-error">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
