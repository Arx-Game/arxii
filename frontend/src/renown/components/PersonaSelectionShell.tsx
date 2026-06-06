import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useRenownEligiblePersonasQuery } from '../queries';

interface Props {
  /** CharacterSheet pk whose eligible personas we render tabs for. */
  characterSheetId: number;
  /** Renders the inner body once a persona is selected. */
  children: (selectedPersonaId: number) => React.ReactNode;
}

/**
 * Shared shell for the two Renown panels (self-view `RenownPanel` and
 * foreign-view `RenownCardPanel`). Owns the persona-selector state +
 * loading/empty handling so the panel bodies can stay focused on their
 * card layouts.
 *
 * Render-prop API: callers receive the effective selected persona id
 * (PRIMARY first, then index-0 fallback) and render their own body.
 */
export function PersonaSelectionShell({ characterSheetId, children }: Props) {
  const { data: personas, isLoading: personasLoading } =
    useRenownEligiblePersonasQuery(characterSheetId);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const effectiveSelectedId =
    selectedId ??
    personas?.find((p) => p.persona_type === 'primary')?.id ??
    personas?.[0]?.id ??
    null;

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

      {effectiveSelectedId !== null && children(effectiveSelectedId)}
    </div>
  );
}
