import { Loader2 } from 'lucide-react';
import { usePersonaRenownQuery } from '../queries';
import { FameCard } from './FameCard';
import { PrestigeBreakdownCard } from './PrestigeBreakdownCard';
import { ReputationListCard } from './ReputationListCard';
import { DeedsLogCard } from './DeedsLogCard';
import { OwnedDwellingsCard } from './OwnedDwellingsCard';
import { TenantedRoomsCard } from './TenantedRoomsCard';
import { PersonaSelectionShell } from './PersonaSelectionShell';
import { SpreadTaleDialog } from '@/spread/SpreadTaleDialog';
import type { RenownPayload } from '../types';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterSheetId: number;
}

/**
 * Top-level Renown tab body. Per spec: a sub-panel per PRIMARY/ESTABLISHED
 * persona on the body. TEMPORARY personas accumulate but don't surface
 * here.
 *
 * Layout:
 *   - Persona selector (handled by the shared `PersonaSelectionShell`).
 *   - The selected persona's renown payload, rendered as four cards:
 *     Fame, Prestige, Reputation, Recent Deeds.
 */
export function RenownPanel({ characterSheetId }: Props) {
  return (
    <PersonaSelectionShell characterSheetId={characterSheetId}>
      {(personaId) => <PanelBody personaId={personaId} />}
    </PersonaSelectionShell>
  );
}

function PanelBody({ personaId }: { personaId: number }) {
  const { data: renown, isLoading } = usePersonaRenownQuery(personaId);
  if (isLoading || !renown) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <SpreadTaleDialog personaId={personaId} />
      </div>
      <CardLayout renown={renown} personaId={personaId} />
    </div>
  );
}

function CardLayout({ renown, personaId }: { renown: RenownPayload; personaId: number }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <FameCard fame={renown.fame} />
      <PrestigeBreakdownCard prestige={renown.prestige} />
      <ReputationListCard reputation={renown.reputation} />
      <DeedsLogCard deeds={renown.recent_deeds} personaId={personaId} />
      <OwnedDwellingsCard dwellings={renown.owned_dwellings} />
      <TenantedRoomsCard rooms={renown.tenanted_rooms} />
    </div>
  );
}
