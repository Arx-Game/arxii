import { CharacterApplicationForm } from './CharacterApplicationForm';
import type { RosterEntryData } from '@/roster/types';
import type { AccountData } from '@/evennia_replacements/types';

interface ApplicationSlotProps {
  entry: RosterEntryData;
  account: AccountData | null;
}

/**
 * Renders the "Apply to Play" slot on the character sheet: a pending-application
 * notice when the viewing account already has a PENDING application for THIS
 * character (matched by `character_id`, added in #2162 task 1), otherwise the
 * application form when the entry is open to applications.
 */
export function ApplicationSlot({ entry, account }: ApplicationSlotProps) {
  const myPendingApp = account?.pending_applications?.find(
    (app) => app.character_id === entry.character.id
  );

  if (myPendingApp) {
    return (
      <section>
        <h3 className="text-xl font-semibold">Apply to Play</h3>
        <p className="rounded-md border bg-muted p-4 text-sm">
          Application pending — submitted {new Date(myPendingApp.applied_date).toLocaleDateString()}
          . Staff will email you when it's reviewed.
        </p>
      </section>
    );
  }

  return entry.can_apply ? <CharacterApplicationForm entryId={entry.id} /> : null;
}
