/**
 * The Sheet section (#3898) — the front of the character sheet.
 *
 * Three short columns, then the folding bands, then the prose. The columns are kept
 * short deliberately: an earlier draft ran the actor's-sheet answers down the middle
 * column and the other two ended in dead space beside it, so everything tall now lives
 * in a full-width band instead.
 *
 * Gating is render-or-vanish. The goals band is absent unless the payload carried
 * goals, the abilities band is absent unless it carried stats or skills, and a viewer
 * who gets neither is offered the rumor band in their place — the page keeps its shape
 * for a stranger, a friend and the character's own player alike.
 */

import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import type {
  CharacterSheetDistinction,
  CharacterSheetGift,
  CharacterSheetGoal,
  CharacterSheetPayload,
} from '@/character_sheets/api';
import { AbilitiesBand } from './AbilitiesBand';
import { BeatsBand } from './BeatsBand';
import { CastRow } from './CastRow';
import { GuidelinesBand } from './GuidelinesBand';
import { Entries, Entry, Glance, Heading, Ledger, Prose, Stack, Tag } from './primitives';
import type { GlanceRow } from './primitives';
import { StaffEditBand, StaffEditable } from './StaffEdit';
import { StaffRowsBand } from './StaffRowsBand';
import { useStaffEditing } from './staffEditContext';

interface SheetPanelProps {
  sheet: CharacterSheetPayload;
  isMyCharacter: boolean;
  /** One rumor about this character, for a viewer who cannot read the guidelines. */
  rumor: string | null;
  /**
   * The "Speaks" line, or null for no row. The page passes this only for the viewer's
   * ACTIVE character, because the languages endpoint is scoped to that character rather
   * than to whichever owned sheet is open.
   */
  languages: string | null;
}

export function SheetPanel({ sheet, isMyCharacter, rumor, languages }: SheetPanelProps) {
  const { identity, story, actor_sheet: actorSheet, distinctions, magic } = sheet;
  // Staff edit mode (#3988): the identity choices drawn at a glance are edited there.
  const editing = useStaffEditing();
  const choice = (
    field: 'species' | 'origin_realm' | 'family' | 'tarot_card' | 'gender',
    label: string,
    name: string | undefined
  ) =>
    editing ? <StaffEditable field={field} kind="choice" label={label} display={name} /> : name;

  const glanceRows: GlanceRow[] = [
    { label: 'Age', value: identity.age },
    { label: 'Born', value: identity.birthday },
    { label: 'Kind', value: choice('species', 'Kind', identity.species?.name) },
    // Beginning is the CG archetype (Caretaker, Sleeper, Misbegotten), and a character
    // may hold more than one; `origin` is the realm they are FROM, which is its own row.
    { label: 'Beginning', value: identity.beginnings.map((row) => row.name).join(', ') },
    { label: 'From', value: choice('origin_realm', 'From', identity.origin?.name) },
    // Plain text, not a link: a Family pk is not an Organization pk, and the org page
    // is member-only besides. The family page (#4209) becomes the destination (#4210).
    { label: 'House', value: choice('family', 'House', identity.family?.name) },
    { label: 'Tarot', value: choice('tarot_card', 'Tarot', identity.tarot_card?.name) },
    { label: 'Gender', value: choice('gender', 'Gender', identity.gender?.name) },
    { label: 'Path', value: identity.path?.name },
    { label: 'Keeps faith with', value: identity.worship?.name },
    { label: 'Lives', value: sheet.current_residence?.name },
    { label: 'Speaks', value: languages },
  ];

  const goals = sheet.goals;
  const hasGuidelines =
    Boolean(actorSheet.never_do || actorSheet.protect || actorSheet.fear) ||
    goals.length > 0 ||
    Boolean(actorSheet.enemy_public_line);
  const hasAbilities = Object.keys(sheet.stats).length > 0 || sheet.skills.length > 0;

  // The private sheet (#4124): the owner's and staff's own reading of the character,
  // set apart by a tone shift and one heading, never by captions. It is drawn only
  // when the payload carries it, so a stranger's page is the public sheet alone.
  const hasPrivate = sheet.beats.length > 0;

  return (
    <Stack wide>
      <StaffEditBand sheet={sheet} />
      <StaffRowsBand />
      {hasPrivate && <Heading>Public sheet</Heading>}
      <div className="refsheet-columns">
        <Stack>
          <Heading>At a glance</Heading>
          <Glance rows={glanceRows} />
        </Stack>

        <Stack wide>
          <TraitsBlock distinctions={distinctions} />
          <GiftBlock magic={magic} isMyCharacter={isMyCharacter} />
        </Stack>

        <CastRow slots={story.origin_slots} />
      </div>

      {hasGuidelines ? (
        <GuidelinesBand block={actorSheet} goals={goals as CharacterSheetGoal[]} />
      ) : (
        rumor && (
          <div className="refsheet-band" style={{ padding: '0.9rem 1.125rem' }}>
            <div className="flex flex-col gap-2">
              <span className="refsheet-eyebrow">Heard of them</span>
              <p className="refsheet-soft italic">{rumor}</p>
            </div>
          </div>
        )
      )}

      {hasAbilities && <AbilitiesBand stats={sheet.stats} skills={sheet.skills} />}

      <div className="refsheet-columns-even">
        {((sheet.appearance.description || '') !== '' || editing) && (
          <Stack>
            <Heading>As they appear</Heading>
            <Prose>
              <p>
                <StaffEditable
                  field="description"
                  kind="prose"
                  label="As they appear"
                  display={sheet.appearance.description}
                />
              </p>
            </Prose>
          </Stack>
        )}
        <OriginsBlock story={story} editing={editing} />
      </div>

      {hasPrivate && (
        <section className="refsheet-private" aria-label="Private sheet">
          <Heading>Private sheet</Heading>
          <BeatsBand beats={sheet.beats} />
        </section>
      )}
    </Stack>
  );
}

/** Distinctions as pills. A disadvantage is dashed and muted, not warned about. */
function TraitsBlock({ distinctions }: { distinctions: CharacterSheetDistinction[] }) {
  if (distinctions.length === 0) return null;
  return (
    <Stack>
      <Heading>Traits</Heading>
      <div className="refsheet-pills">
        {distinctions.map((distinction) => (
          <span
            key={distinction.id}
            className={cn('refsheet-pill', distinction.rank < 0 && 'refsheet-pill-minor')}
            title={distinction.notes || undefined}
          >
            {distinction.name}
          </span>
        ))}
      </div>
    </Stack>
  );
}

/**
 * One gift as one sentence: its name, what it resonates with, and the techniques worked
 * through it. The demo's line reads "Hush, resonant with Silence: Still Room, Thief of
 * Echoes", and every part of that but the tradition is already on the payload. The
 * tradition is not — `GiftEntry` carries no tradition field — so the sentence names what
 * it has rather than leaving a gap where a word should be.
 */
function giftSentence(gift: CharacterSheetGift): string {
  const resonances = gift.resonances.join(', ');
  const techniques = gift.techniques.map((technique) => technique.name).join(', ');
  const opening = resonances ? `${gift.name}, resonant with ${resonances}` : gift.name;
  return techniques ? `${opening}: ${techniques}.` : `${opening}.`;
}

/**
 * The gift in one sentence, pointing at Magic for the rest. The aura lives there
 * (Dan's ruling): it belongs where a reader goes to see how a character's magic fares,
 * not front and centre on a page about who they are.
 */
function GiftBlock({
  magic,
  isMyCharacter,
}: {
  magic: CharacterSheetPayload['magic'];
  isMyCharacter: boolean;
}) {
  if (!magic || magic.gifts.length === 0) return null;
  return (
    <Stack>
      <Heading>Gift</Heading>
      {magic.gifts.map((gift) => (
        <p key={gift.name}>{giftSentence(gift)}</p>
      ))}
      <Ledger>
        {isMyCharacter
          ? 'Their aura, threads and how each fares are on the Magic page.'
          : 'Their aura is on the Magic page.'}
      </Ledger>
    </Stack>
  );
}

/** Where they come from: the formative ties, then the background prose. */
function OriginsBlock({
  story,
  editing,
}: {
  story: CharacterSheetPayload['story'];
  editing: boolean;
}) {
  const groups = story.origin_slots.filter((slot) => slot.kind === 'group');
  if (groups.length === 0 && !story.background && !editing) return null;
  return (
    <Stack>
      <Heading>Where they come from</Heading>
      {(story.background || editing) && (
        <Prose>
          <p>
            <StaffEditable
              field="background"
              kind="prose"
              label="Where they come from"
              display={story.background}
            />
          </p>
        </Prose>
      )}
      {groups.length > 0 && (
        <Entries>
          {groups.map((slot) => (
            <Entry
              key={slot.slot_id}
              name={
                slot.organization_id ? (
                  <Link to={`/orgs/${slot.organization_id}`}>{slot.organization_name}</Link>
                ) : (
                  slot.organization_name || slot.slot_name
                )
              }
              tags={
                <>
                  {slot.connection_kind && <Tag>{slot.connection_kind}</Tag>}
                  {slot.life_stage && <Tag>{slot.life_stage}</Tag>}
                </>
              }
              gloss={slot.choice_description || slot.choice_name || undefined}
            />
          ))}
        </Entries>
      )}
    </Stack>
  );
}
