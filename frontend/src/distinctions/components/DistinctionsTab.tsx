/**
 * DistinctionsTab (#1446) — the character sheet's Distinctions section.
 *
 * Ungated: every viewer sees this tab, because the server already filters secret rows for
 * non-privileged viewers (`_build_distinctions`, src/world/character_sheets/serializers.py:501).
 * This component only renders whatever `useCharacterSheetQuery` returns — it does NOT
 * re-implement privacy client-side — and adds a `Secret` badge on rows where `is_secret` is true.
 */

import { Loader2 } from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useCharacterSheetQuery } from '@/character_sheets/queries';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterId: number;
}

export function DistinctionsTab({ characterId }: Props) {
  const { data: payload, isLoading } = useCharacterSheetQuery(characterId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const distinctions = payload?.distinctions ?? [];

  if (distinctions.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="distinctions-empty-state">
        No distinctions yet.
      </p>
    );
  }

  return (
    <div className="space-y-2" data-testid="distinctions-list">
      {distinctions.map((distinction) => (
        <Card key={distinction.id} data-testid="distinction-row">
          <CardContent className="space-y-1 py-4">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{distinction.name}</span>
              <div className="flex items-center gap-2">
                <Badge variant="outline">{`Rank ${distinction.rank}`}</Badge>
                {distinction.is_secret && <Badge variant="secondary">Secret</Badge>}
              </div>
            </div>
            {distinction.notes && (
              <p className="text-sm text-muted-foreground">{distinction.notes}</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
