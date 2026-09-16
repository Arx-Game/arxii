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
    <section className="space-y-3" data-testid="worship-section">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-xl font-semibold">Worship</h3>
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
      <p className="text-sm text-muted-foreground" data-testid="public-worship">
        {publicWorship ? `Worships ${publicWorship.name}.` : 'No declared faith.'}
      </p>
      {privileged && (
        <div className="space-y-2" data-testid="visions-list">
          <h4 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Visions
          </h4>
          {(visions ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="visions-empty">
              No vision has come.
            </p>
          ) : (
            (visions ?? []).map((vision) => <VisionCard key={vision.id} vision={vision} />)
          )}
        </div>
      )}
      {isStaff && recentPrayers.length > 0 && (
        <div className="space-y-2" data-testid="prayers-list">
          <h4 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Recent prayers (staff)
          </h4>
          <ul className="space-y-1">
            {recentPrayers.map((prayer) => (
              <li key={prayer.id} className="text-sm" data-testid="prayer-row">
                <span className="text-muted-foreground">
                  {formatRelativeTime(prayer.prayed_at)}, to {prayer.being_name}
                  {prayer.dire_straits ? ` (${prayer.dire_straits.replace('_', ' ')})` : ''}
                  {prayer.devotion_granted ? ' (act of devotion)' : ''}
                  {prayer.answered ? ' (answered)' : ''}:
                </span>{' '}
                <span className="whitespace-pre-wrap">{prayer.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
