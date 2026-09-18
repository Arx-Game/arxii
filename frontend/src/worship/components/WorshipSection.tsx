/**
 * WorshipSection (#3779) — the sheet's worship card: the public faith, the character's
 * visions in the treatment reserved for them, the owner's Pray dialog, and for staff the
 * character's recent prayers with the Send-vision composer beside them (a contextual
 * centre: the GM reads the prayer and answers it on the same card).
 *
 * Visions and prayers are IC knowledge: the server returns none for a sheet the viewer does
 * not play, so both lists are fetched only for the owner or staff.
 */

import { formatRelativeTime } from '@/lib/relativeTime';
import { usePrayers, useVisions } from '../queries';
import { PrayDialog } from './PrayDialog';
import { SendVisionDialog } from './SendVisionDialog';
import { VisionCard } from './VisionCard';
import {
  Entries,
  Entry,
  Heading,
  Subheading,
  Tag,
} from '@/character_sheets/components/sheet/primitives';

export interface PublicWorshipRef {
  id: number;
  name: string;
}

interface WorshipSectionProps {
  sheetId: number;
  characterName: string;
  isMyCharacter: boolean;
  isStaff: boolean;
  publicWorship: PublicWorshipRef | null;
}

const RECENT_PRAYERS = 8;

export function WorshipSection({
  sheetId,
  characterName,
  isMyCharacter,
  isStaff,
  publicWorship,
}: WorshipSectionProps) {
  const privileged = isMyCharacter || isStaff;
  const { data: visions } = useVisions(sheetId, privileged);
  const { data: prayers } = usePrayers(sheetId, isStaff);
  const recentPrayers = (prayers ?? []).slice(0, RECENT_PRAYERS);

  return (
    <div className="refsheet-stack" data-testid="worship-section">
      <Heading>Worship</Heading>
      <p className="refsheet-ledger" data-testid="public-worship">
        {publicWorship ? `Keeps faith with ${publicWorship.name}.` : 'No declared faith.'}
      </p>
      {(isMyCharacter || isStaff) && (
        <div className="refsheet-doors">
          {isMyCharacter && (
            <PrayDialog characterId={sheetId} defaultBeingId={publicWorship?.id ?? null} />
          )}
          {isStaff && (
            <SendVisionDialog
              recipientSheetId={sheetId}
              recipientName={characterName}
              prayers={recentPrayers}
            />
          )}
        </div>
      )}
      {privileged && (
        <div className="refsheet-stack" data-testid="visions-list">
          <Subheading>Visions</Subheading>
          {(visions ?? []).length === 0 ? (
            <p className="refsheet-ledger" data-testid="visions-empty">
              No vision has come.
            </p>
          ) : (
            (visions ?? []).map((vision) => <VisionCard key={vision.id} vision={vision} />)
          )}
        </div>
      )}
      {isStaff && recentPrayers.length > 0 && (
        <div className="refsheet-stack" data-testid="prayers-list">
          <Subheading>Recent prayers (staff)</Subheading>
          <Entries>
            {recentPrayers.map((prayer) => (
              <div key={prayer.id} data-testid="prayer-row">
                <Entry
                  name={`To ${prayer.being_name}`}
                  aside={
                    <span className="refsheet-note">{formatRelativeTime(prayer.prayed_at)}</span>
                  }
                  tags={
                    <>
                      {prayer.dire_straits && <Tag>{prayer.dire_straits.replace('_', ' ')}</Tag>}
                      {prayer.devotion_granted && <Tag>act of devotion</Tag>}
                      {prayer.answered && <Tag accent>answered</Tag>}
                    </>
                  }
                  gloss={<span style={{ whiteSpace: 'pre-wrap' }}>{prayer.text}</span>}
                />
              </div>
            ))}
          </Entries>
        </div>
      )}
    </div>
  );
}
