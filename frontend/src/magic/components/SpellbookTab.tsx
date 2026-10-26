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
 * raw affinity percentages.
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): gifts and techniques are entries on
 * hairlines, resonances are a glance list, and the aura is prose under its own
 * subheading. The four workbench links this used to end with are gone: they belonged to
 * a standalone tab with nowhere else to go, and on the sheet they read as a second
 * navigation bar under the section row.
 */

import { useState } from 'react';

import { useCharacterSheetQuery } from '@/character_sheets/queries';
import {
  Entries,
  Entry,
  Ledger,
  Prose,
  Stack,
  Subheading,
  Tag,
} from '@/character_sheets/components/sheet/primitives';
import type { CharacterSheetAura, CharacterSheetTechnique } from '@/character_sheets/api';
import { priceCostParts } from '@/magic/priceCost';
import type { TechniqueForm } from '@/magic/types';
import { MotifStylePanel } from './MotifStylePanel';
import { TechniqueEffectSummaryDisplay } from './TechniqueEffectSummary';
import { TechniqueProgressPanel } from './TechniqueProgressPanel';
import { StaffEditable } from '@/character_sheets/components/sheet/StaffEdit';
import { useStaffEditing } from '@/character_sheets/components/sheet/staffEditContext';
import { GlimpseEditorDialog } from './glimpse/GlimpseEditorDialog';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterId: number;
  /** True when the viewer owns this character — gates the owner-only panels. */
  isMyCharacter: boolean;
  /**
   * Which half of the Magic section this instance is drawing (#3898). The spec and the
   * demo split the page: what a caster DOES (gifts, motif, the owner's workbenches) runs
   * down the main column, and what their magic IS (the aura, the resonances they hold)
   * sits in a narrow rail beside it. Both halves read the same payload through the same
   * cache key, so drawing them as two instances costs nothing.
   *
   * `all` keeps the whole spellbook in one column, which is what a caller outside the
   * sheet would want.
   */
  slot?: 'all' | 'main' | 'rail';
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
  const priceCost = technique.price
    ? priceCostParts(technique.price.consumes, technique.price.inflicts)
    : [];

  if (
    unlocked.length <= 1 &&
    locked.length === 0 &&
    !signature &&
    !technique.price &&
    !technique.next_signature
  )
    return null;

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
                {form.is_default && <Tag>default</Tag>}
                {form.is_early && <Tag>early</Tag>}
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

      {(locked.length > 0 || technique.next_signature) && (
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
          {technique.next_signature && (
            <p className="text-sm text-muted-foreground" data-testid="technique-next-signature">
              {technique.next_signature.name}, at thread level {technique.next_signature.min_level}
            </p>
          )}
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

      {technique.price && (
        <p className="text-sm" data-testid="technique-price">
          <span className="font-medium">Price:</span> {technique.price.name}
          {priceCost.length > 0 && (
            <span
              className="block text-xs text-muted-foreground"
              data-testid="technique-price-cost"
            >
              {priceCost.join(' · ')}
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/** A CSS-safe class suffix for an affinity name ("Celestial" -> "celestial"). */
function affinitySlug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

/**
 * The aura as a proportional strip: one segment per affinity held, sized by its share,
 * with the split said in words underneath rather than printed on them. An aura with
 * nothing in it renders no strip — there is nothing to be proportional to.
 */
function AuraStrip({ aura }: { aura: CharacterSheetAura }) {
  const held = aura.shares.filter((share) => share.percent > 0);
  if (held.length === 0) return null;
  return (
    <div className="refsheet-aura" data-testid="spellbook-aura-strip">
      {held.map((share) => {
        const slug = affinitySlug(share.affinity_name);
        return (
          <span
            key={share.affinity_id}
            className={`refsheet-aura-seg refsheet-aura-${slug}`}
            style={{ flexGrow: share.percent }}
            data-testid={`aura-segment-${slug}`}
          />
        );
      })}
    </div>
  );
}

/** Where the owner stands with their Glimpse, in a line. */
function glimpseStateLine(state: CharacterSheetAura['glimpse_state']): string {
  if (state === 'COMPLETE') return 'Your Glimpse is written.';
  if (state === 'TAGS_ONLY') return 'Your Glimpse has its shape, and no story yet.';
  return 'You have not looked into your own aura yet.';
}

/**
 * A share of the aura, in words. The magic app's standing rule is that player-facing
 * data is narrative rather than numerical, and the sheet's spec asks for the split to
 * be said in words beside the strip — so this is the one place the figures turn
 * into language, and the figures themselves never reach the page.
 */
function shareInWords(share: number, total: number): string {
  const part = total > 0 ? share / total : 0;
  if (part <= 0) return 'none';
  if (part < 0.08) return 'a trace';
  if (part < 0.18) return 'a tenth';
  if (part < 0.28) return 'a fifth';
  if (part < 0.4) return 'a third';
  if (part < 0.58) return 'half';
  if (part < 0.8) return 'most';
  return 'nearly all';
}

/**
 * The aura's split as one sentence: the smaller shares named, the largest called "the
 * rest", in the demo's own shape ("A fifth celestial, a third primal, the rest
 * abyssal."). Silent when the aura is unformed and every share is zero.
 */
function auraSplitSentence(aura: CharacterSheetAura): string {
  const total = aura.shares.reduce((sum, share) => sum + share.percent, 0);
  const held = aura.shares
    .filter((row) => row.percent > 0)
    .map((row) => ({ name: row.affinity_name.toLowerCase(), share: row.percent }))
    .sort((a, b) => a.share - b.share);

  if (held.length === 0) return '';
  if (held.length === 1) return `All of it ${held[0].name}.`;

  const rest = held[held.length - 1];
  const named = held
    .slice(0, -1)
    .map((row) => `${shareInWords(row.share, total)} ${row.name}`)
    .join(', ');
  const sentence = `${named}, the rest ${rest.name}.`;
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

export function SpellbookTab({ characterId, isMyCharacter, slot = 'all' }: Props) {
  const { data: payload, isLoading } = useCharacterSheetQuery(characterId);
  const [glimpseDialogOpen, setGlimpseDialogOpen] = useState(false);
  const staffEditing = useStaffEditing();

  if (isLoading) {
    return <Ledger>Reading their spellbook…</Ledger>;
  }

  const magic = payload?.magic ?? null;
  const drawsMain = slot !== 'rail';
  const drawsRail = slot !== 'main';

  return (
    <Stack wide>
      {magic === null && drawsMain && (
        <p className="refsheet-ledger" data-testid="spellbook-empty-state">
          Nothing is known of their magic.
        </p>
      )}

      {drawsMain && magic && magic.gifts.length > 0 && (
        <div className="refsheet-stack" data-testid="spellbook-gifts">
          {magic.gifts.map((gift) => (
            <Stack key={gift.name} data-testid="spellbook-gift">
              <Subheading>{gift.name}</Subheading>
              {gift.resonances.length > 0 && (
                <div className="refsheet-tags">
                  {gift.resonances.map((resonance) => (
                    <Tag key={resonance}>{resonance}</Tag>
                  ))}
                </div>
              )}
              {gift.description && (
                <Prose>
                  <p>{gift.description}</p>
                </Prose>
              )}
              <Entries>
                {gift.techniques.map((technique) => (
                  <div key={technique.catalog_name} data-testid="spellbook-technique">
                    <Entry
                      name={technique.name}
                      aside={
                        <span className="refsheet-note">
                          {technique.name !== technique.catalog_name
                            ? `${technique.catalog_name} · Level ${technique.level}`
                            : `Level ${technique.level}`}
                        </span>
                      }
                      tags={<Tag>{technique.style}</Tag>}
                      gloss={technique.description || undefined}
                    >
                      <TechniqueEffectSummaryDisplay
                        summary={technique.effect_summary}
                        variant="full"
                      />
                      <TechniqueForms technique={technique} />
                    </Entry>
                  </div>
                ))}
              </Entries>
            </Stack>
          ))}
        </div>
      )}

      {drawsMain && magic && magic.ultimates.length > 0 && (
        <div className="refsheet-stack" data-testid="spellbook-ultimates">
          <Subheading>Ultimates</Subheading>
          <Entries>
            {magic.ultimates.map((ultimate) => (
              <Entry
                key={ultimate.name}
                name={ultimate.name}
                tags={<Tag>{ultimate.label}</Tag>}
                gloss={ultimate.description || undefined}
              />
            ))}
          </Entries>
        </div>
      )}

      {drawsRail && magic && magic.resonances.length > 0 && (
        <div className="refsheet-stack" data-testid="spellbook-resonances">
          <Subheading>Resonances</Subheading>
          <dl className="refsheet-glance">
            {magic.resonances.map((resonance) => (
              <div
                key={resonance.name}
                style={{ display: 'contents' }}
                data-testid="resonance-balance"
              >
                <dt>{resonance.name}</dt>
                <dd>{`${resonance.balance} of ${resonance.lifetime_earned} ever earned`}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {/* The anima ritual: what the caster does to draw on themselves, as a sentence and
          the three things it is worked with. Built server-side since #3001 and never
          rendered until now. */}
      {drawsMain && magic?.anima_ritual && (
        <div className="refsheet-stack" data-testid="spellbook-anima-ritual">
          <Subheading>Anima ritual</Subheading>
          {magic.anima_ritual.description && (
            <Prose>
              <p>{magic.anima_ritual.description}</p>
            </Prose>
          )}
          <div className="refsheet-tags">
            {magic.anima_ritual.stat && <Tag>{magic.anima_ritual.stat}</Tag>}
            {magic.anima_ritual.skill && <Tag>{magic.anima_ritual.skill}</Tag>}
            {magic.anima_ritual.resonance && <Tag accent>{magic.anima_ritual.resonance}</Tag>}
          </div>
        </div>
      )}

      {drawsMain && magic?.motif && (
        <div className="refsheet-stack" data-testid="spellbook-motif">
          <Subheading>Motif</Subheading>
          {magic.motif.description && (
            <Prose>
              <p>{magic.motif.description}</p>
            </Prose>
          )}
          <Entries>
            {magic.motif.resonances.map((resonance) => (
              <Entry
                key={resonance.name}
                name={resonance.name}
                tags={
                  <>
                    {resonance.facets.map((facet) => (
                      <Tag key={facet}>{facet}</Tag>
                    ))}
                    {resonance.styles.map((style) => (
                      <span key={style} data-testid="motif-resonance-style">
                        <Tag accent>{style}</Tag>
                      </span>
                    ))}
                  </>
                }
              />
            ))}
          </Entries>
        </div>
      )}

      {drawsMain && isMyCharacter && magic && <MotifStylePanel characterSheetId={characterId} />}

      {drawsMain && isMyCharacter && magic && (
        <TechniqueProgressPanel characterSheetId={characterId} />
      )}

      {drawsRail && magic?.aura && (
        <div className="refsheet-stack" data-testid="spellbook-aura">
          <Subheading>Aura</Subheading>
          {/* The strip is proportional, never labelled with its figures: the three
              shares size the segments and the sentence beneath says the split in
              words. The demo draws it this way, and the magic app's narrative-not-
              numerical rule is why the numbers stay off the page. */}
          <AuraStrip aura={magic.aura} />
          <Ledger>
            {auraSplitSentence(magic.aura) ||
              `It reads as ${magic.aura.dominant_affinity.toLowerCase()}.`}
          </Ledger>
          {isMyCharacter && <Ledger>{glimpseStateLine(magic.aura.glimpse_state)}</Ledger>}
          {magic.aura.glimpse_tags.length > 0 && (
            <div className="refsheet-tags" data-testid="spellbook-glimpse-tags">
              {magic.aura.glimpse_tags.map((tag) => (
                <Tag key={tag.id}>{tag.name}</Tag>
              ))}
            </div>
          )}
          {/* Staff edit mode (#4224) edits the Glimpse in place, with its history. */}
          {(magic.aura.glimpse_story || staffEditing) && (
            <Prose>
              <p>
                <StaffEditable
                  field="glimpse"
                  kind="prose"
                  label="Glimpse"
                  display={magic.aura.glimpse_story}
                />
              </p>
            </Prose>
          )}
          {isMyCharacter && magic.aura.can_finish_glimpse && (
            <Stack>
              {magic.aura.glimpse_state === 'TAGS_ONLY' && (
                <Ledger>You have chosen the shape of it; write the story when ready.</Ledger>
              )}
              <div className="refsheet-doors">
                <button
                  type="button"
                  className="refsheet-quiet-door"
                  onClick={() => setGlimpseDialogOpen(true)}
                  data-testid="finish-glimpse-button"
                >
                  Finish your Glimpse
                </button>
              </div>
            </Stack>
          )}
        </div>
      )}

      {drawsRail && isMyCharacter && magic?.aura && (
        <GlimpseEditorDialog
          open={glimpseDialogOpen}
          onOpenChange={setGlimpseDialogOpen}
          characterId={characterId}
          aura={magic.aura}
          distinctions={payload?.distinctions ?? []}
        />
      )}
    </Stack>
  );
}
