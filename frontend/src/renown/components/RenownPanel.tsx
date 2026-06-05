import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useRenownEligiblePersonasQuery, usePersonaRenownQuery } from '../queries';
import { FameCard } from './FameCard';
import { PrestigeBreakdownCard } from './PrestigeBreakdownCard';
import { ReputationListCard } from './ReputationListCard';
import { DeedsLogCard } from './DeedsLogCard';

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
 *   - Persona selector (only shown when there are 2+ eligible personas).
 *   - The selected persona's renown payload, rendered as four cards:
 *     Fame, Prestige, Reputation, Recent Deeds.
 */
export function RenownPanel({ characterSheetId }: Props) {
  const { data: personas, isLoading: personasLoading } =
    useRenownEligiblePersonasQuery(characterSheetId);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const effectiveSelectedId =
    selectedId ??
    personas?.find((p) => p.persona_type === 'primary')?.id ??
    personas?.[0]?.id ??
    null;

  const { data: renown, isLoading: renownLoading } = usePersonaRenownQuery(effectiveSelectedId);

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

      {renownLoading || !renown ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <FameCard fame={renown.fame} />
          <PrestigeBreakdownCard prestige={renown.prestige} />
          <ReputationListCard reputation={renown.reputation} />
          <DeedsLogCard deeds={renown.recent_deeds} />
        </div>
      )}
    </div>
  );
}
