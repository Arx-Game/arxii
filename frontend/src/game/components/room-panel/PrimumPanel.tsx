/**
 * The Primum the viewer senses in this place (#5125): "You sense" with one row per
 * substance, and a Harvest button where she can take some. The server writes the block for
 * the viewer's own eyes, so a substance she has not perceived never reaches it.
 */
import type { PrimumBlock } from '@/hooks/types';
import { HarvestRow } from '@/scenes/components/HarvestRow';
import { primumName } from '@/scenes/primumName';

interface PrimumPanelProps {
  primum: PrimumBlock;
  characterId: number | null;
}

export function PrimumPanel({ primum, characterId }: PrimumPanelProps) {
  const offers = characterId === null ? [] : primum.harvestable;
  if (primum.sensed.length === 0 && offers.length === 0) {
    return null;
  }
  return (
    <section className="space-y-1 border-b px-3 py-2" data-testid="primum-panel">
      {primum.sensed.length > 0 && (
        <>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            You sense
          </h4>
          <ul className="space-y-0.5 text-xs">
            {primum.sensed.map((row) => (
              <li key={row.substance_id}>
                {primumName(row.substance_name)}
                {row.step_name && `: ${row.step_name}`}
              </li>
            ))}
          </ul>
        </>
      )}
      {characterId !== null && <HarvestRow offers={offers} characterId={characterId} />}
    </section>
  );
}
