/**
 * PathIntentCard — shows the character's current Path and lets them declare the
 * next Path they're pursuing (or clear a declaration). The Path they choose is
 * pre-selected at their next crossing. Player-facing copy never names the
 * crossing mechanic. Requires a characterId for the X-Character-ID header.
 */

import { useState } from 'react';
import {
  usePathIntent,
  useDeclarePathIntent,
  useClearPathIntent,
  useNextPathOptions,
} from '@/magic/queries';
import { Button } from '@/components/ui/button';

interface PathIntentCardProps {
  characterId: number;
}

export function PathIntentCard({ characterId }: PathIntentCardProps) {
  const { data: optionsData, isLoading } = useNextPathOptions(characterId);
  const { data: intentData } = usePathIntent(characterId);
  const declare = useDeclarePathIntent();
  const clear = useClearPathIntent();
  const [selected, setSelected] = useState<number | null>(null);

  if (isLoading) return null;
  const currentPath = optionsData?.current_path ?? null;
  if (!currentPath) return null;

  const options = optionsData?.options ?? [];
  const declaredId = intentData?.intent?.intended_path.id ?? null;
  const effectiveSelection = selected ?? declaredId;

  return (
    <div
      data-testid="path-intent-card"
      className="rounded-md border border-amber-500/40 bg-amber-950/20 p-3 text-sm"
    >
      <div className="mb-1.5 flex items-center justify-between">
        <span className="font-semibold text-amber-300">Your Path</span>
        {declaredId !== null && (
          <Button
            variant="outline"
            size="sm"
            className="h-6 px-2 py-0 text-xs"
            disabled={clear.isPending}
            onClick={() => clear.mutate(characterId)}
            data-testid="path-intent-clear"
          >
            Clear
          </Button>
        )}
      </div>

      <div className="font-medium text-foreground">{currentPath.name}</div>
      <div className="text-muted-foreground">{currentPath.stage_display}</div>

      {options.length === 0 ? (
        <p className="mt-2 text-muted-foreground" data-testid="path-options-empty">
          No further Paths to pursue yet.
        </p>
      ) : (
        <div className="mt-2 space-y-1">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Pursue next</div>
          {options.map((p) => {
            const isDeclared = p.id === declaredId;
            const isSelected = p.id === effectiveSelection;
            return (
              <button
                key={p.id}
                type="button"
                data-testid={`path-option-${p.id}`}
                aria-pressed={isSelected}
                onClick={() => setSelected(p.id)}
                className={`block w-full rounded border px-2 py-1 text-left ${
                  isSelected ? 'border-amber-400 bg-amber-900/30' : 'border-border'
                }`}
              >
                <span className="font-medium">{p.name}</span>
                {isDeclared && <span className="ml-2 text-xs text-amber-300">(declared)</span>}
                <span className="ml-2 text-xs text-muted-foreground">{p.stage_display}</span>
              </button>
            );
          })}
          <Button
            size="sm"
            className="mt-1 h-7 text-xs"
            disabled={
              declare.isPending || effectiveSelection === null || effectiveSelection === declaredId
            }
            onClick={() => {
              if (effectiveSelection !== null) {
                declare.mutate({ characterId, pathId: effectiveSelection });
              }
            }}
            data-testid="path-intent-declare"
          >
            Declare
          </Button>
        </div>
      )}
    </div>
  );
}
