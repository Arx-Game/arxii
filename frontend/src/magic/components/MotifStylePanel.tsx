/**
 * MotifStylePanel (#2030) — player-facing Motif style-binding management.
 *
 * Lets the owning player bind a Style (from the item catalog) to one of
 * their claimed Resonances, and unbind existing bindings. Mounted below the
 * read-only Motif card in SpellbookTab, own-view only. Always renders (the
 * panel itself explains the "claim a resonance first" empty state) rather
 * than being gated out entirely — mirrors the brief for Task 5 of #2030.
 *
 * Wire contract: MotifStyleViewSet (src/world/magic/views_motif_style.py) —
 * list/bind/unbind dispatch BindMotifStyleAction / UnbindMotifStyleAction /
 * ListMotifStylesAction (src/actions/definitions/motif_style.py). 400s carry
 * a `{detail}` string (audacity cap exceeded, unclaimed resonance, style not
 * bound, etc.) surfaced verbatim below the relevant control.
 */

import { useState, type FormEvent } from 'react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  useBindMotifStyle,
  useCharacterResonances,
  useMotifStyleBindings,
  useStyleCatalog,
  useUnbindMotifStyle,
} from '@/magic/queries';
import type { MotifStyleBinding } from '@/magic/types';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the acting character. */
  characterSheetId: number;
}

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

/** Group bindings by resonance, preserving first-seen resonance order. */
function groupByResonance(
  bindings: MotifStyleBinding[]
): { resonanceId: number; resonanceName: string; bindings: MotifStyleBinding[] }[] {
  const order: number[] = [];
  const groups = new Map<number, { resonanceName: string; bindings: MotifStyleBinding[] }>();
  for (const binding of bindings) {
    const existing = groups.get(binding.resonance_id);
    if (existing) {
      existing.bindings.push(binding);
    } else {
      groups.set(binding.resonance_id, {
        resonanceName: binding.resonance_name,
        bindings: [binding],
      });
      order.push(binding.resonance_id);
    }
  }
  return order.map((resonanceId) => ({ resonanceId, ...groups.get(resonanceId)! }));
}

export function MotifStylePanel({ characterSheetId }: Props) {
  const { data: bindingsData, isLoading: bindingsLoading } = useMotifStyleBindings();
  const { data: catalogData, isLoading: catalogLoading } = useStyleCatalog();
  const { data: resonances = [], isLoading: resonancesLoading } =
    useCharacterResonances(characterSheetId);

  const bind = useBindMotifStyle(characterSheetId);
  const unbind = useUnbindMotifStyle(characterSheetId);

  const [styleId, setStyleId] = useState<number | ''>('');
  const [resonanceId, setResonanceId] = useState<number | ''>('');

  const bindings = bindingsData?.bindings ?? [];
  const styles = catalogData?.results ?? [];
  const groups = groupByResonance(bindings);

  function handleBind(event: FormEvent) {
    event.preventDefault();
    if (styleId === '' || resonanceId === '') return;
    bind.mutate(
      { style_id: styleId, resonance_id: resonanceId },
      {
        onSuccess: () => {
          setStyleId('');
          setResonanceId('');
        },
      }
    );
  }

  return (
    <Card data-testid="motif-style-panel">
      <CardHeader>
        <CardTitle className="text-base">Style Bindings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {bindingsLoading ? (
          <p className="text-sm text-muted-foreground">Loading style bindings…</p>
        ) : bindings.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="motif-style-bindings-empty">
            No styles bound yet.
          </p>
        ) : (
          <div className="space-y-3" data-testid="motif-style-bindings-list">
            {groups.map((group) => (
              <div key={group.resonanceId} data-testid={`motif-style-group-${group.resonanceId}`}>
                <Badge variant="outline">{group.resonanceName}</Badge>
                <ul className="mt-1 space-y-1">
                  {group.bindings.map((binding) => (
                    <li
                      key={binding.style_id}
                      className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm"
                      data-testid="motif-style-binding-row"
                    >
                      <span>
                        {binding.style_name}{' '}
                        <span className="text-muted-foreground">({binding.audacity})</span>
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => unbind.mutate({ style_id: binding.style_id })}
                        disabled={unbind.isPending}
                        data-testid={`unbind-style-${binding.style_id}`}
                      >
                        Unbind
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {unbind.isError ? (
          <p
            role="alert"
            data-testid="motif-style-unbind-error"
            className="text-sm font-medium text-red-500"
          >
            {unbind.error?.message}
          </p>
        ) : null}

        <form
          onSubmit={handleBind}
          className="space-y-2 border-t pt-3"
          data-testid="motif-style-bind-form"
        >
          <Label htmlFor="motif-style-select">Bind a style</Label>
          {resonancesLoading ? (
            <p className="text-sm text-muted-foreground">Loading claimed resonances…</p>
          ) : resonances.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="motif-style-no-resonances">
              Claim a resonance first to bind a style to it.
            </p>
          ) : (
            <div className="flex flex-wrap items-end gap-2">
              <select
                id="motif-style-select"
                data-testid="motif-style-select"
                className={`${SELECT_CLASS} min-w-40 flex-1`}
                value={styleId}
                onChange={(e) => setStyleId(e.target.value === '' ? '' : Number(e.target.value))}
                disabled={catalogLoading}
              >
                <option value="">Select a style…</option>
                {styles.map((style) => (
                  <option key={style.id} value={style.id}>
                    {style.name} ({style.audacity})
                  </option>
                ))}
              </select>
              <select
                id="motif-resonance-select"
                data-testid="motif-resonance-select"
                className={`${SELECT_CLASS} min-w-40 flex-1`}
                value={resonanceId}
                onChange={(e) =>
                  setResonanceId(e.target.value === '' ? '' : Number(e.target.value))
                }
              >
                <option value="">Select a resonance…</option>
                {resonances.map((cr) => (
                  <option key={cr.resonance} value={cr.resonance}>
                    {cr.resonance_name}
                  </option>
                ))}
              </select>
              <Button
                type="submit"
                disabled={styleId === '' || resonanceId === '' || bind.isPending}
                data-testid="motif-style-bind-submit"
              >
                Bind
              </Button>
            </div>
          )}
        </form>

        {bind.isError ? (
          <p
            role="alert"
            data-testid="motif-style-bind-error"
            className="text-sm font-medium text-red-500"
          >
            {bind.error?.message}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
