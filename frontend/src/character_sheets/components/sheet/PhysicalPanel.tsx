/**
 * The Physical section (#3898) — the body, what is on it, and how it fares.
 *
 * Two rulings shape this page. The colour swatches for hair, eyes and skin belong
 * HERE rather than on the plate: they are reference, not identity, and the full palette
 * belongs on the surfaces that choose one (character creation, disguise, shapeshift,
 * modification). And condition is words, not bars: health, wounds, fatigue and age read
 * as sentences for the owner and staff, while everyone else gets the one line looking
 * at someone would tell them. The full-width vitals bars the old sheet opened with are
 * gone — this is not an action game, and a player checks their health, they do not
 * watch it.
 *
 * Worn items show here because they are visible; everything else the character owns or
 * carries is under Holdings.
 */

import { Link } from 'react-router-dom';
import type { CharacterVitalsData } from '@/vitals/vitalsQueries';
import type { CharacterSheetPayload } from '@/character_sheets/api';
import { Entries, Entry, Glance, Heading, Ledger, Prose, Stack, Tag } from './primitives';
import type { GlanceRow } from './primitives';

/**
 * Words for a fatigue zone. The API's zone enum is the authority on which band a pool
 * is in; this only translates it, so a retuned threshold needs no change here.
 */
const ZONE_WORDS: Record<string, string> = {
  fresh: 'fresh',
  tired: 'tired',
  weary: 'weary',
  exhausted: 'exhausted',
  spent: 'spent',
};

interface PhysicalPanelProps {
  sheet: CharacterSheetPayload;
  /** Null for any viewer the vitals endpoint refuses — that is most of them. */
  vitals: CharacterVitalsData | null;
  isPrivileged: boolean;
  /** The outfit and equipped items the character is wearing, if the viewer may see them. */
  worn: WornItem[];
  /** The character's published galleries. Every viewer sees these; they are public. */
  galleries: { name: string; url: string }[];
  /**
   * Opens Holdings, where the wardrobe is. Passed only for the character's own player —
   * the demo puts a "Change outfit" line under Wearing, and it is the one place on this
   * page that leads anywhere the reader can act.
   */
  onOpenHoldings?: () => void;
}

export interface WornItem {
  id: number;
  name: string;
  description: string;
  /** Hidden items render for the owner only, with a line saying so. */
  isHidden: boolean;
}

export function PhysicalPanel({
  sheet,
  vitals,
  isPrivileged,
  worn,
  galleries,
  onOpenHoldings,
}: PhysicalPanelProps) {
  const { appearance, identity } = sheet;

  // The distinctions aimed at a visible feature — a burn, a scar, an unusual eye. They
  // belong beside hair and build because that is where a reader looks for them, and they
  // also stay in the full list under Distinctions.
  const features = sheet.distinctions.filter((row) => row.feature !== '');

  // Height: the band is what anyone can tell by looking; the exact inches are the
  // owner's and staff's, and arrive null for everyone else (#1325).
  const heightValue = buildHeight(appearance.height_band, appearance.height_inches);

  const physiqueRows: GlanceRow[] = [
    { label: 'Height', value: heightValue },
    { label: 'Build', value: appearance.build?.name },
    // Hair, eyes, skin and any other form trait, as the words themselves. No colour
    // swatch: `FormTraitOption` carries no colour value (only name/display_name), and
    // inventing a hex per option here would be a second, drifting vocabulary for
    // something authored content owns. A swatch belongs with a real colour on the
    // option, which is authoring work of its own.
    ...appearance.form_traits.map((trait) => ({
      label: trait.trait,
      value: trait.value,
    })),
  ];

  return (
    <Stack wide>
      <div className="refsheet-columns-even">
        <Stack wide>
          <Stack>
            <Heading>Physique</Heading>
            <Glance rows={physiqueRows} />
            <p className="refsheet-note">
              Colours are set in character creation, and change through disguise, shapeshift or
              modification, where the full palette is offered.
            </p>
          </Stack>

          {features.length > 0 && (
            <Stack>
              <Heading>Distinctive features</Heading>
              <Entries>
                {features.map((feature) => (
                  <Entry
                    key={feature.id}
                    name={feature.name}
                    tags={feature.feature ? <Tag>{feature.feature}</Tag> : undefined}
                    gloss={feature.notes || undefined}
                  />
                ))}
              </Entries>
            </Stack>
          )}

          {worn.length > 0 && (
            <Stack>
              <Heading>Wearing</Heading>
              <Entries>
                {worn.map((item) => (
                  <Entry
                    key={item.id}
                    name={item.name}
                    gloss={
                      item.isHidden ? (
                        <>
                          {item.description} <em>Only you know it is there.</em>
                        </>
                      ) : (
                        item.description || undefined
                      )
                    }
                  />
                ))}
              </Entries>
              {onOpenHoldings && (
                <button type="button" className="refsheet-quiet-door" onClick={onOpenHoldings}>
                  Change outfit
                </button>
              )}
            </Stack>
          )}
        </Stack>

        {isPrivileged && vitals ? (
          <Stack>
            <Heading>Condition</Heading>
            <Glance rows={conditionRows(vitals, identity)} />
            <p className="refsheet-note">
              Yours and the staff&apos;s only. Anima is on the Magic page.
            </p>
          </Stack>
        ) : (
          <Stack>
            <Heading>Condition</Heading>
            <Ledger>{plainSight(vitals)}</Ledger>
          </Stack>
        )}
      </div>

      {appearance.description && (
        <Stack>
          <Heading>As they appear</Heading>
          <Prose>
            <p>{appearance.description}</p>
          </Prose>
        </Stack>
      )}

      {/* Every published gallery, not just whichever one the plate happens to link.
          Images of a character are how they look, so they belong on this page. */}
      {galleries.length > 0 && (
        <Stack>
          <Heading>Galleries</Heading>
          <Entries>
            {galleries.map((gallery) => (
              <Entry key={gallery.url} name={<Link to={gallery.url}>{gallery.name}</Link>} />
            ))}
          </Entries>
        </Stack>
      )}
    </Stack>
  );
}

/**
 * The height line: the band on its own for most viewers, the band plus the exact
 * measure for the owner and staff. No band at all means the character has no height
 * recorded, and the row drops.
 */
function buildHeight(band: string | null, inches: number | null): string | null {
  if (!band) return null;
  if (inches === null) return band;
  return `${band} (${formatHeight(inches)})`;
}

/** Inches as feet and inches, the way a person would say it. */
function formatHeight(inches: number): string {
  const feet = Math.floor(inches / 12);
  const rest = inches % 12;
  return rest === 0 ? `${feet}'` : `${feet}'${rest}"`;
}

/** Health, wounds, fatigue, mood and the age axes, as sentences. */
function conditionRows(
  vitals: CharacterVitalsData,
  identity: CharacterSheetPayload['identity']
): GlanceRow[] {
  const { fatigue } = vitals;
  const pools = [
    `Body ${ZONE_WORDS[fatigue.physical.zone] ?? fatigue.physical.zone}`,
    `mind ${ZONE_WORDS[fatigue.mental.zone] ?? fatigue.mental.zone}`,
    `spirit ${ZONE_WORDS[fatigue.social.zone] ?? fatigue.social.zone}`,
  ].join(', ');

  const ageParts: string[] = [];
  if (identity.age !== null) ageParts.push(`${identity.age} apparent`);
  if (identity.chronological_age !== null) ageParts.push(`${identity.chronological_age} lived`);
  if (identity.biological_age !== null) ageParts.push(`${identity.biological_age} in the body`);
  if (identity.withered_years) ageParts.push(`${identity.withered_years} withered`);

  return [
    {
      label: 'Health',
      value: `${healthWord(vitals)}. ${vitals.health} of ${vitals.max_health}.`,
    },
    { label: 'Wounds', value: vitals.wound_description || 'None that show.' },
    {
      label: 'Fatigue',
      value: `${fatigue.well_rested ? 'Rested' : 'Not rested'}. ${pools}.`,
    },
    { label: 'Mood', value: identity.current_mood?.name },
    { label: 'Age', value: ageParts.length > 0 ? `${ageParts.join(', ')}.` : null },
  ];
}

/** One word for how hale someone is, rather than a bar. */
function healthWord(vitals: CharacterVitalsData): string {
  if (vitals.status !== 'alive') return capitalizeFirst(vitals.status);
  if (vitals.health_percentage >= 0.99) return 'Hale';
  if (vitals.health_percentage >= 0.75) return 'Marked';
  if (vitals.health_percentage >= 0.5) return 'Hurt';
  if (vitals.health_percentage >= 0.25) return 'Badly hurt';
  return 'Failing';
}

/**
 * What a viewer who is not the owner can tell by looking. Deliberately coarse: it
 * names no numbers and no wound description, because the sheet is not a scene and
 * reading someone's condition is something you do in one.
 */
function plainSight(vitals: CharacterVitalsData | null): string {
  if (!vitals) return 'What you can tell by looking is what the scene shows you.';
  if (vitals.status === 'dead') return 'They are dead.';
  if (vitals.status !== 'alive') return 'They are in a bad way.';
  if (vitals.health_percentage >= 0.99) {
    return 'They stand straight and move without favouring anything.';
  }
  return 'They are carrying an injury.';
}

function capitalizeFirst(word: string): string {
  return word.length === 0 ? word : word[0].toUpperCase() + word.slice(1);
}
