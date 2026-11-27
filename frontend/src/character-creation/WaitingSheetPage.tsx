/**
 * The waiting sheet (#5206), at `/characters/create/sheet`.
 *
 * A submitted character's sheet, read while staff review it: the in-game sheet's own plate,
 * section row and panels, drawn from the draft (`GET .../drafts/{id}/sheet/`). Nothing exists
 * in the world before approval, so every panel is handed the payload rather than fetching by
 * a character id, and only the sections a new character has something in are offered.
 *
 * What is left out, and why: staff edit mode (`StaffEditProvider` is never mounted: there is
 * no character to edit), Gallery (a new character has no pictures), and every action or block
 * that needs a character in play: wearing or adding a look, Journal, Friend, the law,
 * agreements, outfits, advancement, sheet updates, stat points, maturation, standoff,
 * messages, clues and gossip.
 *
 * A player's page finds their own draft (an account holds at most one); staff open anyone's
 * with `?draft=<id>`. The server answers 404 for any other draft and for a draft that is not
 * submitted, in review or sent back, and the page reads "Not found." in the sheet's frame.
 */

import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import '@/character_sheets/sheet.css';
import type { CharacterSheetPayload } from '@/character_sheets/api';
import { Plate } from '@/character_sheets/components/sheet/Plate';
import { glanceLines } from '@/character_sheets/components/sheet/glanceLines';
import { SectionRow, type SheetSection } from '@/character_sheets/components/sheet/SectionRow';
import { SheetPanel } from '@/character_sheets/components/sheet/SheetPanel';
import { PhysicalPanel } from '@/character_sheets/components/sheet/PhysicalPanel';
import {
  CarriedBlock,
  DistinctionsPanel,
  DomainsBlock,
  KeyringBlock,
  MagicPanel,
  OriginStoryAnswers,
  PurseBlock,
} from '@/character_sheets/components/sheet/panels';
import { Entries, Entry, Heading, Stack } from '@/character_sheets/components/sheet/primitives';
import { LanguagesSection } from '@/character_sheets/components/LanguagesSection';
import { XpLedgerCard } from '@/progression/components/advancement/XpLedgerCard';
import { OrganizationStandingBlock } from '@/reputation/components/ReputationTab';
import { SecretsTab } from '@/secrets/components/SecretsTab';
import { useDraft, useWaitingSheet } from './queries';
import type { WaitingSheetPayload } from './types';

/** No character exists yet, so every panel that takes an id is given none (0 asks nothing). */
const NO_SHEET = 0;

/** The sections this page can offer, in the sheet's own order; Gallery never. */
function offeredSections(payload: WaitingSheetPayload): SheetSection[] {
  const { standing, secrets } = payload;
  const hasTies = standing.memberships.length > 0 || standing.reputations.length > 0;
  return [
    'sheet',
    'physical',
    ...(hasTies ? (['ties'] as const) : []),
    'distinctions',
    'magic',
    ...(secrets.length > 0 ? (['knowledge'] as const) : []),
    'estate',
    'growth',
  ];
}

export function WaitingSheetPage() {
  const [searchParams] = useSearchParams();
  const requested = Number(searchParams.get('draft')) || undefined;
  // Staff name the draft; a player's own is the one draft their account holds.
  const ownDraft = useDraft(requested === undefined);
  const draftId = requested ?? ownDraft.data?.id;
  const sheetQuery = useWaitingSheet(draftId);
  const [section, setSection] = useState<SheetSection>('sheet');

  if (ownDraft.isLoading || sheetQuery.isLoading) {
    return <WaitingFrame>Loading...</WaitingFrame>;
  }
  if (sheetQuery.isError) {
    return <WaitingFrame>The sheet could not be read. Try again.</WaitingFrame>;
  }
  const payload = sheetQuery.data;
  if (!draftId || !payload) return <WaitingFrame>Not found.</WaitingFrame>;

  // The panels are typed for the in-game payload, whose `id` is the character's. The
  // waiting sheet has none, and every panel here is handed data rather than an id.
  const sheet: CharacterSheetPayload = { ...payload, id: NO_SHEET };
  const sections = offeredSections(payload);
  const shown = sections.includes(section) ? section : 'sheet';
  const spoken = payload.languages.filter((row) => row.fluency > 0).map((row) => row.name);

  return (
    <div className="refsheet" data-ink={payload.plate_ink ?? 'ember'}>
      <Plate
        name={payload.identity.fullname}
        titles={[]}
        concept={payload.identity.concept ?? ''}
        quote={payload.identity.quote ?? ''}
        glanceLines={glanceLines(payload)}
        looks={[]}
        canWear={false}
        onWear={() => undefined}
        isSaving={false}
        mark={<span className="refsheet-waiting">Awaiting approval</span>}
      />
      <SectionRow current={shown} onSelect={setSection} isMyCharacter sections={sections} />

      <div className="refsheet-leaf">
        {shown === 'sheet' && (
          <SheetPanel
            sheet={sheet}
            isMyCharacter
            rumor={null}
            languages={spoken.length ? spoken.join(', ') : null}
          />
        )}

        {shown === 'physical' && (
          <PhysicalPanel sheet={sheet} vitals={null} isPrivileged worn={[]} />
        )}

        {shown === 'ties' && (
          <Stack>
            <Heading>Organizations</Heading>
            <OrganizationStandingBlock standing={payload.standing} />
          </Stack>
        )}

        {shown === 'distinctions' && <DistinctionsPanel sheetId={NO_SHEET} payload={sheet} />}

        {shown === 'magic' && (
          <MagicPanel sheetId={NO_SHEET} isMyCharacter={false} payload={sheet} />
        )}

        {shown === 'knowledge' && (
          <Stack>
            <Heading>Secrets</Heading>
            <SecretsTab subjectId={NO_SHEET} viewerId={null} secrets={payload.secrets} />
          </Stack>
        )}

        {shown === 'estate' && (
          <Stack wide>
            <div className="refsheet-columns-3">
              <PurseBlock balance={payload.purse.balance} />
              <CarriedBlock items={payload.carried} />
              {payload.current_residence && (
                <Stack>
                  <Heading>Property</Heading>
                  <Entries>
                    <Entry name={payload.current_residence.name} />
                  </Entries>
                </Stack>
              )}
            </div>
            <div className="refsheet-columns-even">
              <DomainsBlock domains={payload.domains} />
              <KeyringBlock keyring={payload.keyring} />
            </div>
          </Stack>
        )}

        {shown === 'growth' && (
          <div className="refsheet-columns-2">
            <Stack wide>
              <Stack>
                <Heading>Advancement</Heading>
                <XpLedgerCard sheetId={NO_SHEET} ledger={payload.xp_ledger} />
              </Stack>
            </Stack>
            <Stack wide>
              <Stack>
                <Heading>Languages</Heading>
                <LanguagesSection languages={payload.languages} />
              </Stack>
              <OriginStoryAnswers slots={payload.story.origin_slots} />
            </Stack>
          </div>
        )}
      </div>
    </div>
  );
}

/** The sheet's frame around a single line, for loading, an error or a missing sheet. */
function WaitingFrame({ children }: { children: string }) {
  return (
    <div className="refsheet" data-ink="ember">
      <div className="refsheet-leaf">
        <p className="refsheet-ledger">{children}</p>
      </div>
    </div>
  );
}
