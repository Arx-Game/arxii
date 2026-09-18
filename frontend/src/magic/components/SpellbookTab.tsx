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
import type { TechniqueForm } from '@/magic/types';
import { MotifStylePanel } from './MotifStylePanel';
import { TechniqueEffectSummaryDisplay } from './TechniqueEffectSummary';
import { TechniqueProgressPanel } from './TechniqueProgressPanel';
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
                {form.is_default && <Tag>default</Tag>}
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

/**
 * The aura as a proportional strip: three segments sized by their share, with the split
 * said in words underneath rather than printed on them. An aura with nothing in it
 * renders no strip — there is nothing to be proportional to.
 */
function AuraStrip({ aura }: { aura: CharacterSheetAura }) {
  const total = aura.celestial + aura.primal + aura.abyssal;
  if (total <= 0) return null;
  const segments: Array<[string, number]> = [
    ['celestial', aura.celestial],
    ['primal', aura.primal],
    ['abyssal', aura.abyssal],
  ];
  return (
    <div className="refsheet-aura" data-testid="spellbook-aura-strip">
      {segments
        .filter(([, share]) => share > 0)
        .map(([name, share]) => (
          <span
            key={name}
            className={`refsheet-aura-${name}`}
            style={{ flexGrow: share }}
            data-testid={`aura-segment-${name}`}
          />
        ))}
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
 * be said in words beside the strip — so this is the one place the three figures turn
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
  const total = aura.celestial + aura.primal + aura.abyssal;
  const held = [
    { name: 'celestial', share: aura.celestial },
    { name: 'primal', share: aura.primal },
    { name: 'abyssal', share: aura.abyssal },
  ]
    .filter((row) => row.share > 0)
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

export function SpellbookTab({ characterId, isMyCharacter, slot = 'all' }: Props) {
  const { data: payload, isLoading } = useCharacterSheetQuery(characterId);
  const [glimpseDialogOpen, setGlimpseDialogOpen] = useState(false);

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
                  <div key={technique.name} data-testid="spellbook-technique">
                    <Entry
                      name={technique.name}
                      aside={<span className="refsheet-note">{`Level ${technique.level}`}</span>}
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
              `It reads as ${dominantAffinityLabel(magic.aura).toLowerCase()}.`}
          </Ledger>
          {isMyCharacter && <Ledger>{glimpseStateLine(magic.aura.glimpse_state)}</Ledger>}
          {magic.aura.glimpse_tags.length > 0 && (
            <div className="refsheet-tags" data-testid="spellbook-glimpse-tags">
              {magic.aura.glimpse_tags.map((tag) => (
                <Tag key={tag.id}>{tag.name}</Tag>
              ))}
            </div>
          )}
          {magic.aura.glimpse_story && (
            <Prose>
              <p>{magic.aura.glimpse_story}</p>
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
