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

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useCharacterSheetQuery } from '@/character_sheets/queries';
import type { CharacterSheetAura, CharacterSheetTechnique } from '@/character_sheets/api';
import type { TechniqueForm } from '@/magic/types';
import { MotifStylePanel } from './MotifStylePanel';
import { TechniqueEffectSummaryDisplay } from './TechniqueEffectSummary';
import { GlimpseEditorDialog } from './glimpse/GlimpseEditorDialog';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterId: number;
  /** True when the viewer owns this character — gates the workbench link-outs. */
  isMyCharacter: boolean;
}

/**
 * Which forms of one technique this caster can work (#2901).
 *
 * A variant does not replace the technique, so this is a list: the base form,
 * each unlocked resonance-specialized form, and one step ahead as a goal. The
 * sheet describes, so it carries the whole catalogue; the in-scene cast list
 * carries only a compact affordance.
 *
 * Silent when the caster has only the base form and nothing ahead of them —
 * a one-item list would say nothing the technique's own name did not.
 */
function TechniqueForms({ technique }: { technique: CharacterSheetTechnique }) {
  const unlocked = technique.forms.filter((form) => !form.is_locked);
  const locked = technique.forms.filter((form) => form.is_locked);
  const { signature } = technique;

  if (unlocked.length <= 1 && locked.length === 0 && !signature) return null;

  const label = (form: TechniqueForm) =>
    form.variant_id === null ? 'base form' : `${form.name} (${form.resonance_name})`;

  return (
    <div className="mt-2 space-y-2 border-t pt-2" data-testid="technique-forms">
      {(unlocked.length > 1 || locked.length > 0) && (
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Forms you can work
          </p>
          {unlocked.map((form) => (
            <div key={form.variant_id ?? 'base'} data-testid="technique-form">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm">{label(form)}</span>
                {form.is_default && (
                  <Badge variant="secondary" className="text-xs">
                    default
                  </Badge>
                )}
                <span className="text-xs text-muted-foreground">
                  intensity {form.intensity}, control {form.control}
                </span>
              </div>
              {form.variant_id !== null && (
                <TechniqueEffectSummaryDisplay
                  summary={form.effect_summary}
                  variant="compact"
                  className="mt-0.5"
                />
              )}
            </div>
          ))}
        </div>
      )}

      {locked.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Not yet yours
          </p>
          {locked.map((form) => (
            <p
              key={form.variant_id ?? 'base'}
              className="text-sm text-muted-foreground"
              data-testid="technique-form-locked"
            >
              {label(form)}, at thread level {form.unlock_thread_level}
            </p>
          ))}
        </div>
      )}

      {signature && (
        <p className="text-sm" data-testid="technique-signature">
          <span className="font-medium">Signature:</span> {signature.name} (
          {signature.intensity_delta >= 0 ? '+' : ''}
          {signature.intensity_delta} intensity)
          {signature.narrative_snippet && (
            <span className="block text-xs italic text-muted-foreground">
              {signature.narrative_snippet}
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/** The affinity with the highest share, as a qualitative label — never the raw percentage. */
function dominantAffinityLabel(aura: CharacterSheetAura): string {
  const shares: Array<[string, number]> = [
    ['Celestial', aura.celestial],
    ['Primal', aura.primal],
    ['Abyssal', aura.abyssal],
  ];
  return shares.reduce(
    (dominant, share) => (share[1] > dominant[1] ? share : dominant),
    shares[0]
  )[0];
}

export function SpellbookTab({ characterId, isMyCharacter }: Props) {
  const { data: payload, isLoading } = useCharacterSheetQuery(characterId);
  const [glimpseDialogOpen, setGlimpseDialogOpen] = useState(false);

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
                    <TechniqueEffectSummaryDisplay
                      summary={technique.effect_summary}
                      variant="full"
                      className="mt-1"
                    />
                    <TechniqueForms technique={technique} />
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
                {resonance.styles.map((style) => (
                  <Badge key={style} variant="default" data-testid="motif-resonance-style">
                    {style}
                  </Badge>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {isMyCharacter && magic && <MotifStylePanel characterSheetId={characterId} />}

      {magic?.aura && (
        <Card data-testid="spellbook-aura">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <span>Aura</span>
              <Badge variant="outline">{dominantAffinityLabel(magic.aura)}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {magic.aura.glimpse_tags.length > 0 && (
              <div className="flex flex-wrap gap-1" data-testid="spellbook-glimpse-tags">
                {magic.aura.glimpse_tags.map((tag) => (
                  <Badge key={tag.id} variant="secondary">
                    {tag.name}
                  </Badge>
                ))}
              </div>
            )}
            {magic.aura.glimpse_story && (
              <p className="text-sm text-muted-foreground">{magic.aura.glimpse_story}</p>
            )}
            {isMyCharacter && magic.aura.can_finish_glimpse && (
              <div className="space-y-2 pt-1">
                {magic.aura.glimpse_state === 'TAGS_ONLY' && (
                  <p className="text-sm text-muted-foreground">
                    You&rsquo;ve chosen the shape of it; write the story when ready.
                  </p>
                )}
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setGlimpseDialogOpen(true)}
                  data-testid="finish-glimpse-button"
                >
                  Finish your Glimpse
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {isMyCharacter && magic?.aura && (
        <GlimpseEditorDialog
          open={glimpseDialogOpen}
          onOpenChange={setGlimpseDialogOpen}
          characterId={characterId}
          aura={magic.aura}
          distinctions={payload?.distinctions ?? []}
        />
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
