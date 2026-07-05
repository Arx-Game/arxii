/**
 * SpellbookTab (#1446) — the character sheet's Magic section.
 *
 * DESIGN RULING: "The sheet describes; the scene does." This is a spellbook/status view
 * ONLY — gifts, techniques, motif, and aura rendered as read-only prose/data. NO cast
 * buttons, invocation UI, or any way to *do* magic from here — casting stays scene-contextual.
 *
 * Ungated: every viewer sees this tab, because the server already gates `payload.magic` to
 * null for foreign viewers without visibility AND for magic-less characters (`_build_magic`,
 * src/world/character_sheets/serializers.py) — this component only renders whatever
 * `useCharacterSheetQuery` returns; it does NOT re-implement visibility client-side.
 *
 * Aura is rendered qualitatively per the magic app's key rule ("player-facing data is
 * narrative, not numerical") — the glimpse_story plus a dominant-affinity label, never the
 * raw celestial/primal/abyssal percentages.
 */

import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useCharacterSheetQuery } from '@/character_sheets/queries';
import type { CharacterSheetAura } from '@/character_sheets/api';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterId: number;
  /** True when the viewer owns this character — gates the workbench link-outs. */
  isMyCharacter: boolean;
}

/** The affinity with the highest share, as a qualitative label — never the raw percentage. */
function dominantAffinityLabel(aura: CharacterSheetAura): string {
  const shares: Array<[string, number]> = [
    ['Celestial', aura.celestial],
    ['Primal', aura.primal],
    ['Abyssal', aura.abyssal],
  ];
  return shares.reduce((dominant, share) => (share[1] > dominant[1] ? share : dominant))[0];
}

export function SpellbookTab({ characterId, isMyCharacter }: Props) {
  const { data: payload, isLoading } = useCharacterSheetQuery(characterId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const magic = payload?.magic ?? null;

  return (
    <div className="space-y-4">
      {magic === null && (
        <p className="py-8 text-center text-muted-foreground" data-testid="spellbook-empty-state">
          Nothing is known of their magic.
        </p>
      )}

      {magic && magic.gifts.length > 0 && (
        <div className="space-y-2" data-testid="spellbook-gifts">
          <h3 className="text-lg font-semibold">Gifts</h3>
          {magic.gifts.map((gift) => (
            <Card key={gift.name} data-testid="spellbook-gift">
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
                  <span>{gift.name}</span>
                  <div className="flex flex-wrap gap-1">
                    {gift.resonances.map((resonance) => (
                      <Badge key={resonance} variant="outline">
                        {resonance}
                      </Badge>
                    ))}
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {gift.description && (
                  <p className="text-sm text-muted-foreground">{gift.description}</p>
                )}
                {gift.techniques.map((technique) => (
                  <div
                    key={technique.name}
                    className="rounded-md border p-3"
                    data-testid="spellbook-technique"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">{technique.name}</span>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">{technique.style}</Badge>
                        <Badge variant="outline">{`Level ${technique.level}`}</Badge>
                      </div>
                    </div>
                    {technique.description && (
                      <p className="text-sm text-muted-foreground">{technique.description}</p>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {magic?.motif && (
        <Card data-testid="spellbook-motif">
          <CardHeader>
            <CardTitle className="text-base">Motif</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {magic.motif.description && (
              <p className="text-sm text-muted-foreground">{magic.motif.description}</p>
            )}
            {magic.motif.resonances.map((resonance) => (
              <div key={resonance.name} className="flex flex-wrap items-center gap-1">
                <Badge variant="outline">{resonance.name}</Badge>
                {resonance.facets.map((facet) => (
                  <Badge key={facet} variant="secondary">
                    {facet}
                  </Badge>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {magic?.aura && (
        <Card data-testid="spellbook-aura">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <span>Aura</span>
              <Badge variant="outline">{dominantAffinityLabel(magic.aura)}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {magic.aura.glimpse_story && (
              <p className="text-sm text-muted-foreground">{magic.aura.glimpse_story}</p>
            )}
          </CardContent>
        </Card>
      )}

      {isMyCharacter && (
        <div className="flex flex-wrap gap-4 border-t pt-4 text-sm text-muted-foreground">
          <Link to="/magic/progression" className="hover:underline">
            Progression
          </Link>
          <Link to="/threads" className="hover:underline">
            Threads
          </Link>
          <Link to="/sanctums" className="hover:underline">
            Sanctums
          </Link>
          <Link to="/rituals" className="hover:underline">
            Rituals
          </Link>
        </div>
      )}
    </div>
  );
}
