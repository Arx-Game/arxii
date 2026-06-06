import { Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { usePersonaRenownCardQuery } from '../queries';
import { DeedsLogCard } from './DeedsLogCard';
import { ReputationListCard } from './ReputationListCard';
import { PersonaSelectionShell } from './PersonaSelectionShell';
import type { RenownCardPayload } from '../types';

interface Props {
  /** CharacterSheet pk of the target (foreign) character. */
  characterSheetId: number;
  /** The viewer's currently-presented persona, or null when unknown. */
  viewerPersonaId: number | null;
}

/**
 * Limited renown view shown on someone else's character sheet. Spec:
 * fame tier label only (no numeric reveal), deeds filtered to those
 * the viewer's societies have heard about, reputation rows for the
 * viewer's societies only.
 *
 * Symmetric layout to ``RenownPanel`` for the parts that still apply,
 * minus prestige numbers + dwellings/items breakdowns — those are
 * intentionally not surfaced for foreign personas.
 */
export function RenownCardPanel({ characterSheetId, viewerPersonaId }: Props) {
  return (
    <PersonaSelectionShell characterSheetId={characterSheetId}>
      {(personaId) => <CardBody personaId={personaId} viewerPersonaId={viewerPersonaId} />}
    </PersonaSelectionShell>
  );
}

function CardBody({
  personaId,
  viewerPersonaId,
}: {
  personaId: number;
  viewerPersonaId: number | null;
}) {
  const { data: card, isLoading } = usePersonaRenownCardQuery(personaId, viewerPersonaId);
  if (isLoading || !card) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  return <CardLayout card={card} />;
}

function CardLayout({ card }: { card: RenownCardPayload }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Fame</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Badge variant="outline" className="text-base">
              {card.fame.tier_label}
            </Badge>
            <p className="text-xs text-muted-foreground">As your circles read them.</p>
          </div>
        </CardContent>
      </Card>
      <ReputationListCard reputation={card.visible_reputation} />
      <DeedsLogCard deeds={card.visible_deeds} />
    </div>
  );
}
