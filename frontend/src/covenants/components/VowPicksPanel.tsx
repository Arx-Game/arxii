/**
 * A vow holder's focus picks on their own sheet's Covenant block (#4929, demo screen 8).
 *
 * One block per primary vow: its vow level, then each pick level with what is spent of
 * its budget and every pick the vow offers there (the anchor's and the sub-role's
 * together). A chosen pick is marked, a pick that cannot be taken now is dimmed with
 * why, and a pick that can is chosen with its button, through the action dispatch.
 * Budget left unspent simply stays left.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Heading, Stack, Tag } from '@/character_sheets/components/sheet/primitives';
import type { VowPickCatalog, VowPickEntry, VowPickLevel } from '../api';
import { useChooseVowPick, useVowPicks } from '../queries';

function points(price: number): string {
  return `${price} ${price === 1 ? 'pt' : 'pts'}`;
}

function Meter({ budget, spent }: { budget: number; spent: number }) {
  return (
    <span className="vowpicks-meter" aria-hidden="true">
      {Array.from({ length: budget }, (_, index) => (
        <i key={index} className={index < spent ? 'on' : undefined} />
      ))}
    </span>
  );
}

function PickRow({
  pick,
  onChoose,
  pending,
}: {
  pick: VowPickEntry;
  onChoose: () => void;
  pending: boolean;
}) {
  const mechanics = [...pick.effects, pick.limits, pick.locked_reason].filter(Boolean).join(' · ');
  let state = 'open';
  if (pick.chosen) state = 'chosen';
  else if (pick.locked_reason) state = 'locked';
  return (
    <div className={`vowpicks-entry vowpicks-${state}`} data-testid="vow-pick">
      <span className="vowpicks-mark" aria-label={pick.chosen ? 'Chosen' : undefined}>
        {pick.chosen ? '◆' : '◇'}
      </span>
      <span className="refsheet-entry-name">{pick.name}</span>
      <span className="refsheet-note">{points(pick.price)}</span>
      {pick.description && <span className="vowpicks-gloss">{pick.description}</span>}
      <span className="vowpicks-mech">{mechanics}</span>
      {pick.choosable && (
        <span className="vowpicks-choose">
          <Button type="button" size="sm" variant="outline" onClick={onChoose} disabled={pending}>
            Choose
          </Button>
        </span>
      )}
    </div>
  );
}

function LevelBlock({
  level,
  onChoose,
  pending,
}: {
  level: VowPickLevel;
  onChoose: (pickId: number) => void;
  pending: boolean;
}) {
  return (
    <div className="vowpicks-level">
      <div className="vowpicks-level-head">
        <h3 className="refsheet-subheading">Level {level.level}</h3>
        {level.is_open ? (
          <span className="vowpicks-spend">
            <Meter budget={level.budget} spent={level.spent} />
            <span className="refsheet-note">
              {level.spent} of {level.budget}
            </span>
          </span>
        ) : (
          <span className="refsheet-note vowpicks-locked-note">
            opens at vow level {level.level}
          </span>
        )}
      </div>
      {level.picks.map((pick) => (
        <PickRow key={pick.id} pick={pick} pending={pending} onChoose={() => onChoose(pick.id)} />
      ))}
    </div>
  );
}

function VowBlock({ catalog, sheetId }: { catalog: VowPickCatalog; sheetId: number }) {
  const choose = useChooseVowPick(sheetId);
  const [message, setMessage] = useState<string | null>(null);
  const onChoose = (pickId: number) => {
    setMessage(null);
    choose.mutate(
      { covenantId: catalog.covenant_id, pickId },
      { onSuccess: (line) => setMessage(line) }
    );
  };
  return (
    <Stack>
      <div className="vowpicks-head">
        <Heading>{catalog.vow} · vow picks</Heading>
        <Tag>Vow level {catalog.vow_level}</Tag>
      </div>
      {catalog.levels.map((level) => (
        <LevelBlock
          key={level.level}
          level={level}
          onChoose={onChoose}
          pending={choose.isPending}
        />
      ))}
      {choose.isError && (
        <p className="refsheet-note vowpicks-error" role="alert">
          {choose.error.message}
        </p>
      )}
      {message && !choose.isError && (
        <p className="refsheet-note" role="status">
          {message}
        </p>
      )}
    </Stack>
  );
}

/** Every primary vow's picks for the character's owner; nothing when they hold none. */
export function VowPicksPanel({ sheetId }: { sheetId: number }) {
  const { data } = useVowPicks(sheetId);
  if (!data || data.length === 0) return null;
  return (
    <>
      {data.map((catalog) => (
        <VowBlock key={catalog.membership_id} catalog={catalog} sheetId={sheetId} />
      ))}
    </>
  );
}
