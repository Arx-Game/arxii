/**
 * The character sheet (#3898) — the Reference Sheet.
 *
 * The page is the reference sheet an artist makes for a character they love: a plate
 * with the art, the name and the character's own words, then eight sections rather than
 * sixteen tabs, with the three only the player reads set apart on the line.
 *
 * What this page owns is the composition and the gating. Every section's content comes
 * from panels that already existed and keep their own queries; the sheet payload it
 * fetches once feeds the plate, the front and Physical.
 */

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAccount } from '@/store/hooks';
import { useRosterEntryQuery, useMyRosterEntriesQuery, useWearLook } from '../queries';
import { useBrowsingIdentity } from '../useBrowsingIdentity';
import { ApplicationSlot } from '@/components/character';
import { MessagesSection } from '@/narrative/components/MessagesSection';
import { FriendButton } from '@/friends/components/FriendButton';
import { RivalButton } from '@/friends/components/RivalButton';
import { OriginStoryEditorDialog } from '@/character_sheets/components/OriginStoryEditorDialog';
import { MaturationPanel } from '@/character_sheets/components/MaturationPanel';
import { StatPointPanel } from '@/character_sheets/components/StatPointPanel';
import { WorshipSection, type PublicWorshipRef } from '@/worship/components/WorshipSection';
import { useCharacterSheetQuery } from '@/character_sheets/queries';
import { useCharacterVitalsQuery } from '@/vitals/vitalsQueries';
import { useEquippedItems, useInventory } from '@/inventory/hooks/useInventory';
import { usePersonaTitles } from '@/achievements/queries';
import '@/character_sheets/sheet.css';
import { Plate } from '@/character_sheets/components/sheet/Plate';
import { SectionRow, type SheetSection } from '@/character_sheets/components/sheet/SectionRow';
import { SheetPanel } from '@/character_sheets/components/sheet/SheetPanel';
import { PhysicalPanel, type WornItem } from '@/character_sheets/components/sheet/PhysicalPanel';
import {
  DistinctionsPanel,
  GrowthPanel,
  HoldingsPanel,
  KnowledgePanel,
  MagicPanel,
  TiesPanel,
} from '@/character_sheets/components/sheet/panels';
import { Heading, Stack } from '@/character_sheets/components/sheet/primitives';

export function CharacterSheetPage() {
  const { id } = useParams();
  const entryId = Number(id);
  const { data: entry, isLoading } = useRosterEntryQuery(entryId);
  const { data: myEntries } = useMyRosterEntriesQuery();
  const account = useAccount();
  const [section, setSection] = useState<SheetSection>('sheet');

  const isMyCharacter = myEntries?.some((e) => e.id === entryId) ?? false;
  const sheetId = entry?.character.id ?? 0;
  const { data: sheet } = useCharacterSheetQuery(sheetId);

  // Vitals are owner/staff-gated server-side: the query resolves null for anyone else,
  // which is exactly what Physical's plain-sight arm renders from.
  const { data: vitals = null } = useCharacterVitalsQuery(sheetId);

  // See the previous revision of this file for why each of these is resolved the way it
  // is — the reasons are unchanged by the redesign.
  const viewerPersonaId = myEntries?.[0]?.primary_persona_id ?? null;
  const viewedMyEntry = myEntries?.find((e) => e.id === entryId);
  const viewedPersonaId = viewedMyEntry?.primary_persona_id ?? null;
  const titlesPersonaId = viewedPersonaId ?? sheet?.personas[0]?.id ?? null;
  const { entryId: viewerEntryId } = useBrowsingIdentity();
  const isActiveCharacter = viewerEntryId === entryId;

  // Titles compose into the name on the plate, so the page reads them here rather than
  // leaving them to a panel of their own.
  const { data: titles } = usePersonaTitles(titlesPersonaId);

  // What they are wearing, for Physical. Owner-only: the public "what can I see on
  // them" endpoint is same-room gated (it answers the look command), so a roster
  // visitor has no business asking it and would only get a 403.
  const { data: equipped = [] } = useEquippedItems(isMyCharacter ? sheetId : undefined);
  const { data: inventory = [] } = useInventory(isMyCharacter ? sheetId : undefined);

  const wearLook = useWearLook(entryId, sheetId);

  if (isLoading) return <p className="p-4">Loading...</p>;
  if (!entry) return <p className="p-4">Character not found.</p>;

  // A viewer who is not the owner must never be left on one of the three own-only
  // sections — switching characters keeps the section, so this falls back rather than
  // rendering a panel whose queries would all refuse.
  const shown: SheetSection =
    !isMyCharacter && (section === 'knowledge' || section === 'holdings' || section === 'growth')
      ? 'sheet'
      : section;

  const displayName = sheet?.identity.fullname || entry.fullname || entry.character.name;
  const titleNames = (titles ?? []).map((row) => row.title).filter(Boolean);

  const worn: WornItem[] = equipped.map((row) => {
    const item = inventory.find((candidate) => candidate.id === row.item_instance);
    return {
      id: row.id,
      name: item?.display_name ?? row.body_region_display,
      description: item?.display_description ?? row.equipment_layer_display,
      isHidden: false,
    };
  });

  return (
    <div className="refsheet">
      <Plate
        name={displayName}
        titles={titleNames}
        concept={sheet?.identity.concept ?? entry.character.concept ?? ''}
        quote={sheet?.identity.quote ?? entry.quote ?? ''}
        glanceLines={glanceLines(sheet)}
        looks={sheet?.looks ?? []}
        canWear={isMyCharacter}
        onWear={(look) => wearLook.mutate(look.tenure_media_id)}
        isSaving={wearLook.isPending}
        galleriesTo={isMyCharacter ? '/profile/media' : null}
        actions={
          !isMyCharacter && (
            <>
              <FriendButton
                viewerEntryId={viewerEntryId}
                targetEntryId={entryId}
                targetName={entry.character.name}
              />
              <RivalButton
                viewerEntryId={viewerEntryId}
                targetEntryId={entryId}
                targetName={entry.character.name}
              />
            </>
          )
        }
      />

      <SectionRow current={shown} onSelect={setSection} isMyCharacter={isMyCharacter} />

      <div className="refsheet-leaf">
        {shown === 'sheet' && (
          <Stack wide>
            {sheet && (
              <SheetPanel
                sheet={sheet}
                isMyCharacter={isMyCharacter}
                rumor={null}
                languages={null}
              />
            )}
            <WorshipSection
              sheetId={sheetId}
              characterName={entry.character.name}
              isMyCharacter={isMyCharacter}
              isStaff={Boolean(account?.is_staff)}
              publicWorship={(sheet?.identity.worship as PublicWorshipRef | null) ?? null}
            />
            <ApplicationSlot entry={entry} account={account} />
            {isMyCharacter && (
              <div id="messages">
                <MessagesSection />
              </div>
            )}
          </Stack>
        )}

        {shown === 'physical' && sheet && (
          <PhysicalPanel
            sheet={sheet}
            vitals={vitals}
            isPrivileged={isMyCharacter || Boolean(account?.is_staff)}
            worn={worn}
            galleries={entry.character.galleries ?? []}
          />
        )}

        {shown === 'ties' && (
          <TiesPanel
            sheetId={sheetId}
            entryId={entryId}
            isMyCharacter={isMyCharacter}
            viewerPersonaId={viewerPersonaId}
            viewedPersonaId={viewedPersonaId}
            titlesPersonaId={titlesPersonaId}
          />
        )}

        {shown === 'distinctions' && <DistinctionsPanel sheetId={sheetId} />}

        {shown === 'magic' && <MagicPanel sheetId={sheetId} isMyCharacter={isMyCharacter} />}

        {shown === 'knowledge' && isMyCharacter && (
          <KnowledgePanel
            sheetId={sheetId}
            viewerEntryId={viewerEntryId}
            isStaff={Boolean(account?.is_staff)}
          />
        )}

        {shown === 'holdings' && isMyCharacter && (
          <HoldingsPanel
            sheetId={sheetId}
            viewedPersonaId={viewedPersonaId}
            isActiveCharacter={isActiveCharacter}
            viewerEntryId={viewerEntryId}
          />
        )}

        {shown === 'growth' && isMyCharacter && (
          <Stack wide>
            <GrowthPanel
              sheetId={sheetId}
              isMyCharacter={isMyCharacter}
              isActiveCharacter={isActiveCharacter}
              originStoryEditor={
                sheet ? <OriginStoryEditorDialog characterId={sheetId} sheet={sheet} /> : undefined
              }
            />
            <Stack>
              <Heading>Points to place</Heading>
              <StatPointPanel sheetId={sheetId} />
              <MaturationPanel sheetId={sheetId} />
            </Stack>
          </Stack>
        )}
      </div>
    </div>
  );
}

/**
 * The two short lines under the quote: who they are, then what they look like.
 *
 * Both are built from whatever the payload actually carried, so a sparse character
 * gets a shorter line rather than a line full of "TBD" — the failure the old Stats
 * block made unmissable.
 */
function glanceLines(sheet: ReturnType<typeof useCharacterSheetQuery>['data']): string[] {
  if (!sheet) return [];
  const { identity, appearance } = sheet;

  const who = [
    identity.species?.name,
    identity.origin?.name && `Of ${identity.origin.name}`,
    identity.family?.name,
    identity.age !== null ? `${identity.age}` : null,
  ]
    .filter(Boolean)
    .join('. ');

  const looks = [
    appearance.height_band,
    appearance.build?.name,
    ...appearance.form_traits.map((trait) => trait.value),
  ]
    .filter(Boolean)
    .join('. ');

  return [who ? `${who}.` : '', looks ? `${looks}.` : ''].filter(Boolean);
}
