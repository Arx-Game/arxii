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
  CharacterSheetGoal,
  CharacterSheetPayload,
} from '@/character_sheets/api';
import { AbilitiesBand } from './AbilitiesBand';
import { CastRow } from './CastRow';
import { GuidelinesBand } from './GuidelinesBand';
import { Entries, Entry, Glance, Heading, Ledger, Prose, Stack, Tag } from './primitives';
import type { GlanceRow } from './primitives';

interface SheetPanelProps {
  sheet: CharacterSheetPayload;
  isMyCharacter: boolean;
  /** One rumor about this character, for a viewer who cannot read the guidelines. */
  rumor: string | null;
  /** Languages line — the owner's own, so it only renders on their sheet. */
  languages: string | null;
}

export function SheetPanel({ sheet, isMyCharacter, rumor, languages }: SheetPanelProps) {
  const { identity, story, actor_sheet: actorSheet, distinctions, magic } = sheet;

  const glanceRows: GlanceRow[] = [
    { label: 'Age', value: identity.age },
    { label: 'Born', value: identity.birthday },
    { label: 'Kind', value: identity.species?.name },
    { label: 'Beginning', value: identity.origin?.name },
    {
      label: 'House',
      value: identity.family?.name ? (
        <Link to={`/orgs/${identity.family.id}`}>{identity.family.name}</Link>
      ) : null,
    },
    { label: 'Tarot', value: identity.tarot_card?.name },
    { label: 'Gender', value: identity.gender?.name },
    { label: 'Path', value: identity.path?.name },
    { label: 'Keeps faith with', value: identity.worship?.name },
    { label: 'Lives', value: sheet.current_residence?.name },
    { label: 'Speaks', value: isMyCharacter ? languages : null },
  ];

  const goals = sheet.goals;
  const hasGuidelines =
    Boolean(actorSheet.never_do || actorSheet.protect || actorSheet.fear) ||
    goals.length > 0 ||
    Boolean(actorSheet.enemy_public_line);
  const hasAbilities = Object.keys(sheet.stats).length > 0 || sheet.skills.length > 0;

  return (
    <Stack wide>
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
        {(sheet.appearance.description || '') !== '' && (
          <Stack>
            <Heading>As they appear</Heading>
            <Prose>
              <p>{sheet.appearance.description}</p>
            </Prose>
          </Stack>
        )}
        <OriginsBlock story={story} />
      </div>
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
  const names = magic.gifts.map((gift) => gift.name).join(', ');
  return (
    <Stack>
      <Heading>Gift</Heading>
      <p>{names}</p>
      <Ledger>
        {isMyCharacter
          ? 'Their aura, threads and how each fares are on the Magic page.'
          : 'Their aura is on the Magic page.'}
      </Ledger>
    </Stack>
  );
}

/** Where they come from: the formative ties, then the background prose. */
function OriginsBlock({ story }: { story: CharacterSheetPayload['story'] }) {
  const groups = story.origin_slots.filter((slot) => slot.kind === 'group');
  if (groups.length === 0 && !story.background) return null;
  return (
    <Stack>
      <Heading>Where they come from</Heading>
      {story.background && (
        <Prose>
          <p>{story.background}</p>
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
