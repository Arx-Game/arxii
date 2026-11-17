/**
 * The Primum the viewer senses in this place (#5125): "You sense" with one row per
 * substance, and a Harvest Primum block where she can take some. The server writes the block
 * for the viewer's own eyes, so a substance she has not perceived never reaches it. The
 * block's answer is held here, so it stays on screen after the lair empties.
 */
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { PrimumBlock } from '@/hooks/types';
import { primumName, type HarvestAnswer } from '@/scenes/harvestAnswer';
import { HarvestPanel } from '@/scenes/components/HarvestPanel';

interface PrimumPanelProps {
  primum: PrimumBlock;
  characterId: number | null;
}

export function PrimumPanel({ primum, characterId }: PrimumPanelProps) {
  const [open, setOpen] = useState(false);
  const [answer, setAnswer] = useState<HarvestAnswer | null>(null);
  const offers = characterId ? primum.harvestable : [];
  // The lair emptied under an open block with nothing to show: close it.
  if (open && offers.length === 0 && answer === null) {
    setOpen(false);
  }
  const showHarvest = Boolean(characterId) && (open || answer !== null);

  if (primum.sensed.length === 0 && offers.length === 0 && !answer) {
    return null;
  }
  return (
    <section className="space-y-1 border-b px-3 py-2" data-testid="primum-panel">
      {!showHarvest && primum.sensed.length > 0 && (
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
      {characterId && showHarvest && (
        <HarvestPanel
          offers={offers}
          characterId={characterId}
          answer={answer}
          onAnswer={setAnswer}
          onCancel={() => {
            setOpen(false);
            setAnswer(null);
          }}
        />
      )}
      {characterId && !showHarvest && offers.length > 0 && (
        <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
          Harvest Primum
        </Button>
      )}
    </section>
  );
}
