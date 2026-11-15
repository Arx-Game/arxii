/**
 * AuraReflections (#5124, Screen 6 of the approved demo): the aura card's reflections.
 *
 * Under the halo, for the owner only: the reflections written since the last rite of settling
 * ("Your reflections", each with the writing that carries it), one "Settle your aura" button
 * that opens the rite, shown only while a reflection waits, and "Not yet reflected on": the
 * kindled deeds no reflection names, with the open chance to atone when one is open. Renders
 * nothing when there is nothing to list.
 */

import { useState } from 'react';
import { Subheading } from '@/character_sheets/components/sheet/primitives';
import { Button } from '@/components/ui/button';
import {
  usePendingDriftConversionOffers,
  useReflectionOptions,
  useSettlingRite,
} from '@/magic/queries';
import { atoneChanceLine } from '@/magic/riteText';
import { SettleAuraDialog } from './SettleAuraDialog';

interface Props {
  /** CharacterSheet pk (the character's own pk). */
  characterSheetId: number;
}

export function AuraReflections({ characterSheetId }: Props) {
  const [settleOpen, setSettleOpen] = useState(false);
  const { data: rite } = useSettlingRite(characterSheetId);
  const { data: options } = useReflectionOptions(characterSheetId);
  const { data: offers } = usePendingDriftConversionOffers();

  const reflections = rite?.reflections ?? [];
  const deeds = (options ?? []).filter((option) => option.kind === 'deed');
  const chance = atoneChanceLine(
    offers?.results?.find((offer) => offer.character_id === characterSheetId)
  );

  if (reflections.length === 0 && deeds.length === 0 && !chance) return null;

  return (
    <div className="refsheet-stack" data-testid="aura-reflections">
      {reflections.length > 0 ? (
        <>
          <Subheading>Your reflections</Subheading>
          <ul className="refsheet-ledger space-y-1" data-testid="aura-reflections-waiting">
            {reflections.map((reflection) => (
              <li key={reflection.id}>
                {reflection.where ? `${reflection.where} · ` : ''}
                {reflection.title}
              </li>
            ))}
          </ul>
          <div>
            <Button size="sm" onClick={() => setSettleOpen(true)} data-testid="settle-aura-button">
              Settle your aura
            </Button>
          </div>
        </>
      ) : null}
      {deeds.length > 0 || chance ? (
        <>
          <Subheading>Not yet reflected on</Subheading>
          <ul className="refsheet-ledger space-y-1" data-testid="aura-reflections-deeds">
            {deeds.map((deed) => (
              <li key={deed.id}>{deed.label}</li>
            ))}
          </ul>
          {chance ? (
            <p className="refsheet-ledger" data-testid="aura-atone-chance">
              {chance}
            </p>
          ) : null}
        </>
      ) : null}
      <SettleAuraDialog
        characterSheetId={characterSheetId}
        open={settleOpen}
        onOpenChange={setSettleOpen}
      />
    </div>
  );
}
