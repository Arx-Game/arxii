import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { useRenownEligiblePersonasQuery, usePersonaRenownCardQuery } from '../queries';
import { DeedsLogCard } from './DeedsLogCard';
import { ReputationListCard } from './ReputationListCard';
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
  const { data: personas, isLoading: personasLoading } =
    useRenownEligiblePersonasQuery(characterSheetId);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const effectiveSelectedId =
    selectedId ??
    personas?.find((p) => p.persona_type === 'primary')?.id ??
    personas?.[0]?.id ??
    null;

  const { data: card, isLoading: cardLoading } = usePersonaRenownCardQuery(
    effectiveSelectedId,
    viewerPersonaId
  );

  if (personasLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!personas || personas.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No personas with renown to display.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {personas.length > 1 && (
        <Tabs value={String(effectiveSelectedId)} onValueChange={(v) => setSelectedId(Number(v))}>
          <TabsList>
            {personas.map((p) => (
              <TabsTrigger key={p.id} value={String(p.id)}>
                {p.name}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      )}

      {cardLoading || !card ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <CardLayout card={card} />
      )}
    </div>
  );
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
