import { useState } from 'react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Ledger } from '@/character_sheets/components/sheet/primitives';
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
 *
 * Both panels are reached only through the character sheet's Ties section, so the
 * loading and empty arms are drawn in the sheet's voice (#3898): a quiet line, never a
 * bordered card whose whole body is an apology for an empty section.
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
    return <Ledger>Reading what they are known for…</Ledger>;
  }

  if (!personas || personas.length === 0) {
    return <Ledger>No face of theirs is known for anything yet.</Ledger>;
  }

  return (
    <div className="refsheet-stack">
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
