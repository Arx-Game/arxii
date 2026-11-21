/**
 * Stage 8: Appearance (#3630; the controls as the owner ruled them in #5241).
 *
 * The stage is short fields and compact pickers:
 *
 * - Age and the birthday share a line. The birthday is typed as two numbers, month
 *   then day, and read back as "Day 14 of <the game's name for that month>"; a row
 *   of twelve month names a new player cannot place in the year is gone.
 * - Height band and build are dropdowns on one line with the height in inches.
 * - Each physical feature is one `TraitBlock`: a strip of swatches for a colour, a
 *   dropdown for anything else, two across. Under each sits its qualities line
 *   (`FeatureDistinctions`: Alluring, Menacing, Majestic), always on the page.
 *
 * The first `draft.feature_points_free` points of qualities cost no CG points; the
 * heading and the side panel say how many are spent. A feature holding any tier is
 * distinctive: it reaches every option its trait carries and opens its description.
 *
 * Between the height line and the features, `ChapterOffers` mounts this chapter's
 * own offered distinctions (`chapter="appearance"`, #3675 Task 15), one block per
 * authored section (#3709). A height band's own `cg_hint` column (#3675 fix round
 * 1) reads under the height field when staff wrote one, never a name match against
 * a literal band name.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { ChapterLeaf, Field, Marginalia, Note, RecordRail, stageEyebrow } from '../folio';
import {
  useBuilds,
  useCGExplanations,
  useDraftOffers,
  useFormOptions,
  useHeightBands,
  useUpdateDraft,
} from '../queries';
import { formatHeight } from '../utils';
import { useShownPicks } from '../useShownPicks';
import { ChapterOffers } from './offers/ChapterOffers';
import { MarkingsEditor } from './MarkingsEditor';
import { TraitBlock } from './appearance/TraitBlock';
import { Stage } from '../types';
import type { CharacterDraft, FormTraitOption, HeightBand } from '../types';

interface AppearanceStageProps {
  draft: CharacterDraft;
  isStaff?: boolean;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => (() => void) | void;
}

interface AppearanceFormValues {
  description: string;
}

// The age range comes from the draft payload (`age_min` / `age_max`, #3663):
// the server composes the general cap, eternal youth (#2756) and the heritage's
// first appearance, so the folio never has to know the rule.
const AGE_DEFAULT = 22;

// Month names come from the draft payload (`ic_month_names`, #4185); the game's
// calendar keeps the Gregorian layout, so the day counts below still hold.
// 29 for February: leap-day birthdays are legal (#2756).
const DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/** A typed number held to a range, or null when the text is not a number. */
function clampedInt(text: string, min: number, max: number): number | null {
  const parsed = parseInt(text, 10);
  return Number.isNaN(parsed) ? null : Math.max(min, Math.min(max, parsed));
}

export function AppearanceStage({
  draft,
  isStaff = false,
  onRegisterBeforeLeave,
}: AppearanceStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  // The chapter's own offers, read once here to know its sections (#3709); each
  // section's block re-reads the same cached query through `ChapterOffers`.
  const { data: appearanceOffers } = useDraftOffers(draft.id, 'appearance');
  const sections = useMemo(() => {
    const seen = new Map<string, string>();
    for (const offer of appearanceOffers?.offers ?? []) {
      // A quality (#3739) is not a section: it is offered on every feature and
      // marking, and `FeatureDistinctions` mounts it there.
      if (offer.taken_per_feature) continue;
      if (offer.opener_key && !seen.has(offer.opener_key)) {
        seen.set(offer.opener_key, offer.opener_label);
      }
    }
    return Array.from(seen, ([key, label]) => ({ key, label }));
  }, [appearanceOffers]);
  // Whether staff have authored any quality. Without one there is no qualities
  // line on any feature, so the page says nothing about feature points either.
  const hasQualities = (appearanceOffers?.offers ?? []).some((o) => o.taken_per_feature);
  const { data: heightBands, isLoading: heightBandsLoading } = useHeightBands();
  const { data: builds, isLoading: buildsLoading } = useBuilds();
  const { data: formOptions, isLoading: formOptionsLoading } = useFormOptions(
    draft.selected_species?.id,
    draft.id
  );
  const draftData = draft.draft_data;
  // The picks as the page shows them (#5141): a click on a tier shows at once, so
  // the feature it lands on opens at once and the points lines move with it.
  const shown = useShownPicks(draft);
  // Which traits hold a tier of any quality (#5241). That is what opens the widened
  // palette and the description field; the server reads the same thing off the
  // draft's own entries (`offers.opened_features`).
  const openedTraits = useMemo(
    () => new Set(shown.picks.map((pick) => pick.feature_trait).filter(Boolean)),
    [shown.picks]
  );

  // Traits the species offers directly (#2815); a trait id absent from this
  // set but present in `formOptions.inherited` is a stray pinned value (e.g.
  // from a family line) with no own-palette row of its own.
  const ownTraitIds = useMemo(
    () => new Set((formOptions?.traits ?? []).map((t) => t.trait.id)),
    [formOptions]
  );
  const inheritedOptionsFor = useCallback(
    (traitId: number): FormTraitOption[] =>
      (formOptions?.inherited ?? [])
        .filter((group) => group.trait.id === traitId)
        .flatMap((group) => group.options),
    [formOptions]
  );
  const strayInherited = useMemo(
    () => (formOptions?.inherited ?? []).filter((group) => !ownTraitIds.has(group.trait.id)),
    [formOptions, ownTraitIds]
  );

  const { register, getValues, formState } = useForm<AppearanceFormValues>({
    defaultValues: {
      description: draftData.description ?? '',
    },
  });

  const saveDescription = useCallback(async () => {
    if (!formState.isDirty) return true;
    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: {
          draft_data: {
            description: getValues('description'),
          },
        },
      });
      return true;
    } catch {
      return window.confirm('Failed to save description. Discard changes and continue?');
    }
  }, [draft.id, updateDraft, formState.isDirty, getValues]);

  useEffect(() => {
    if (!onRegisterBeforeLeave) return;
    // Return the unregister as cleanup (2026-07 audit): without it, an
    // unmounted stage's save closure stayed registered and re-fired on every
    // later navigation, PATCHing stale values over newer edits.
    return onRegisterBeforeLeave(saveDescription) ?? undefined;
  }, [onRegisterBeforeLeave, saveDescription]);

  const [localAge, setLocalAge] = useState(String(draft.age ?? AGE_DEFAULT));
  const ageMin = draft.age_min;
  const ageMax = draft.age_max;
  const heritage = draft.selected_beginnings?.heritage ?? null;

  // Auto-save default age on first visit when unset, so backend sees age != None
  useEffect(() => {
    if (draft.age === null || draft.age === undefined) {
      updateDraft.mutate({ draftId: draft.id, data: { age: AGE_DEFAULT } });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.id]);

  const commitAge = () => {
    const clamped = clampedInt(localAge, ageMin, ageMax) ?? AGE_DEFAULT;
    setLocalAge(String(clamped));
    if (clamped !== draft.age) {
      updateDraft.mutate({
        draftId: draft.id,
        data: { age: clamped },
      });
    }
  };

  // Celebrated birthday (#2756), the waking day for Sleeper beginnings. Typed as
  // two numbers (#5241) and saved once both are there: a month alone is not a
  // birthday, and the server wants both or neither.
  const [bdayMonth, setBdayMonth] = useState(String(draft.birthday_month ?? ''));
  const [bdayDay, setBdayDay] = useState(String(draft.birthday_day ?? ''));

  const commitBirthday = () => {
    const month = clampedInt(bdayMonth, 1, 12);
    if (month === null) return;
    setBdayMonth(String(month));
    const day = clampedInt(bdayDay, 1, DAYS_IN_MONTH[month - 1]);
    if (day === null) return;
    setBdayDay(String(day));
    if (month !== draft.birthday_month || day !== draft.birthday_day) {
      updateDraft.mutate({
        draftId: draft.id,
        data: { birthday_month: month, birthday_day: day },
      });
    }
  };

  // What is saved, in the game's own words. Read from the draft, not the inputs,
  // so the line confirms the save.
  const birthdayWords =
    draft.birthday_month && draft.birthday_day
      ? `Day ${draft.birthday_day} of ${draft.ic_month_names[draft.birthday_month - 1]}`
      : undefined;

  const handleHeightBandSelect = (band: HeightBand) => {
    const midpoint = Math.floor((band.min_inches + band.max_inches) / 2);
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        height_band_id: band.id,
        height_inches: midpoint,
      },
    });
  };

  // Local buffer while typing; null once committed, so display tracks the
  // draft value again (including a band swap's midpoint reset).
  const [heightInput, setHeightInput] = useState<string | null>(null);

  const commitHeightInches = () => {
    const band = draft.height_band;
    if (!band) return;
    const clamped = clampedInt(heightInput ?? '', band.min_inches, band.max_inches);
    if (clamped !== null && clamped !== draft.height_inches) {
      updateDraft.mutate({
        draftId: draft.id,
        data: { height_inches: clamped },
      });
    }
    setHeightInput(null);
  };

  const handleFormTraitChange = (traitName: string, optionId: number | null) => {
    const nextFormTraits = { ...(draftData.form_traits ?? {}) };
    if (optionId === null) {
      delete nextFormTraits[traitName];
    } else {
      nextFormTraits[traitName] = optionId;
    }
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          form_traits: nextFormTraits,
        },
      },
    });
  };

  // #2632: optional per-trait flavor text ("red" + "flowing crimson"). The
  // normalized option stays the succinct/mechanical value; this text is what
  // other characters read. Commit-on-blur to avoid a per-keystroke PATCH storm.
  const getTraitDescriptor = (traitName: string): string => {
    const descriptors = draftData.form_trait_descriptors as Record<string, string> | undefined;
    return descriptors?.[traitName] ?? '';
  };

  const handleTraitDescriptorCommit = (traitName: string, text: string) => {
    if (text.trim() === getTraitDescriptor(traitName).trim()) return;
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draftData,
          form_trait_descriptors: {
            ...((draftData.form_trait_descriptors as Record<string, string>) ?? {}),
            [traitName]: text.trim(),
          },
        },
      },
    });
  };

  const getSelectedOptionId = (traitName: string): number | null => {
    const formTraits = draftData.form_traits as Record<string, number> | undefined;
    return formTraits?.[traitName] ?? null;
  };

  // The last tier came off a feature, so it is no longer distinctive. A colour only
  // a distinctive feature may hold is let go here; left in place, the stage would
  // report it as not available to the species.
  const handleTraitClosed = (traitName: string, ordinaryIds: Set<number>) => {
    const selected = getSelectedOptionId(traitName);
    if (selected !== null && !ordinaryIds.has(selected)) {
      handleFormTraitChange(traitName, null);
    }
  };

  // Staff see the bands and builds players are not normally offered, marked.
  const staffOnly = (selectable: boolean) =>
    !selectable && isStaff ? ' (not normally offered)' : '';

  const freePoints = draft.feature_points_free;
  const freeSpent = Math.min(shown.featureSpent, freePoints);
  const paidPoints = shown.featureSpent - freeSpent;

  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Species', value: draft.selected_species?.name },
          { label: 'Age', value: draft.age !== null ? String(draft.age) : undefined },
          { label: 'Birthday', value: birthdayWords },
          {
            label: 'Height',
            value:
              draft.height_band && draft.height_inches !== null
                ? `${draft.height_band.display_name}, ${formatHeight(draft.height_inches)}`
                : undefined,
          },
          { label: 'Build', value: draft.build?.display_name },
          ...(hasQualities
            ? [
                {
                  label: 'Feature points',
                  value:
                    paidPoints > 0
                      ? `${freeSpent} of ${freePoints} spent, ${paidPoints} from CG points`
                      : `${freeSpent} of ${freePoints} spent`,
                },
              ]
            : []),
        ]}
        ledger={stageEyebrow(draft.current_stage)}
      />
      <Marginalia id="note-appearance">
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Age">
          must be between {ageMin} and {ageMax} years.
          {heritage?.first_appeared_ic_year != null && (
            <>
              {' '}
              The first {heritage.name} were born in {heritage.first_appeared_ic_year} AS.
            </>
          )}
        </Note>
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Birthday">
          is the day your character celebrates each year. Friends will see it coming up in the Town
          Crier’s tidings.
        </Note>
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Height">
          is a category first and an exact figure within it second.
          {draft.height_band && (
            <>
              {' '}
              Other characters see you as “{draft.height_band.display_name}” rather than your exact
              height.
            </>
          )}
        </Note>
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Build">is your character’s body type.</Note>
        {draft.selected_species && (
          // PLACEHOLDER: Apostate rewrite
          <Note lead="Physical features">
            are drawn from the palette your species offers, plus anything a parent line passes down.
          </Note>
        )}
        {hasQualities && (
          // PLACEHOLDER: Apostate rewrite
          <Note lead="Qualities">
            go on any feature or marking. The first {freePoints} tiers are free; more cost CG
            points.
          </Note>
        )}
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Physical description">
          is optional, and is appended to the automatic description.
        </Note>
        {/* Moved from MarkingsEditor.tsx, which has no margin of its own. */}
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Markings">
          are tattoos, scars, brands and birthmarks: what your character’s skin remembers. Clothing
          conceals a marking at the regions it covers; revealing garments and the in-game reveal
          bare it. Optional.
        </Note>
      </Marginalia>
    </>
  );

  const ageHint = draft.selected_species?.eternal_youth
    ? 'Your species keeps its eternal youth; apparent age locks in the early twenties.'
    : // Unseeded copy key today; renders nothing until staff write it.
      copy?.appearance_age_hint;

  return (
    <ChapterLeaf
      stage={Stage.APPEARANCE}
      title={copy?.appearance_heading ?? 'Appearance'}
      intro={copy?.appearance_intro}
      aside={rail}
    >
      <div className="field-row">
        <Field id="age" label={copy?.appearance_age_heading ?? 'Age'} className="narrow">
          <input
            id="age"
            type="number"
            min={ageMin}
            max={ageMax}
            value={localAge}
            onChange={(e) => setLocalAge(e.target.value)}
            onBlur={commitAge}
          />
        </Field>
        <div className="field birthday" role="group" aria-labelledby="bday-label">
          <span className="label" id="bday-label">
            {copy?.appearance_birthday_heading ?? 'Birthday'}
          </span>
          <span className="birthday-inputs">
            <input
              type="number"
              min={1}
              max={12}
              placeholder="Month"
              aria-label="Birthday month"
              value={bdayMonth}
              onChange={(e) => setBdayMonth(e.target.value)}
              onBlur={commitBirthday}
            />
            <input
              type="number"
              min={1}
              max={31}
              placeholder="Day"
              aria-label="Birthday day"
              value={bdayDay}
              onChange={(e) => setBdayDay(e.target.value)}
              onBlur={commitBirthday}
            />
            {birthdayWords && <span className="birthday-words">{birthdayWords}</span>}
          </span>
        </div>
      </div>
      {ageHint && <p className="ledger-line">{ageHint}</p>}

      <div className="field-row">
        {heightBandsLoading ? (
          <p className="ledger-line" aria-busy="true">
            Loading height bands…
          </p>
        ) : (
          <Field
            id="height-band"
            label={copy?.appearance_height_heading ?? 'Height'}
            hint={draft.height_band?.cg_hint || undefined}
          >
            <select
              id="height-band"
              value={draft.height_band?.id ?? ''}
              onChange={(e) => {
                const band = (heightBands ?? []).find((b) => b.id === Number(e.target.value));
                if (band) handleHeightBandSelect(band);
              }}
            >
              {!draft.height_band && (
                <option value="" disabled>
                  Select
                </option>
              )}
              {(heightBands ?? []).map((band) => (
                <option key={band.id} value={band.id} title={band.cg_hint || undefined}>
                  {band.display_name}
                  {staffOnly(band.is_cg_selectable)}
                </option>
              ))}
            </select>
          </Field>
        )}
        {draft.height_band && (
          <Field
            id="height"
            label="Inches"
            className="narrow"
            hint={`${formatHeight(draft.height_band.min_inches)} to ${formatHeight(
              draft.height_band.max_inches
            )}`}
          >
            <input
              id="height"
              type="number"
              min={draft.height_band.min_inches}
              max={draft.height_band.max_inches}
              value={heightInput ?? String(draft.height_inches ?? '')}
              onChange={(e) => setHeightInput(e.target.value)}
              onBlur={commitHeightInches}
            />
          </Field>
        )}
        {buildsLoading ? (
          <p className="ledger-line" aria-busy="true">
            Loading builds…
          </p>
        ) : (
          <Field id="build" label={copy?.appearance_build_heading ?? 'Build'}>
            <select
              id="build"
              value={draft.build?.id ?? ''}
              onChange={(e) => {
                const build = (builds ?? []).find((b) => b.id === Number(e.target.value));
                if (build) updateDraft.mutate({ draftId: draft.id, data: { build_id: build.id } });
              }}
            >
              {!draft.build && (
                <option value="" disabled>
                  Select
                </option>
              )}
              {(builds ?? []).map((build) => (
                <option key={build.id} value={build.id}>
                  {build.display_name}
                  {staffOnly(build.is_cg_selectable)}
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>

      {/* What shows, in sections (#3709): one offers block per authored Appearance
          section, in the sections' own order. A card the route closes is absent and
          named nowhere (#4979). */}
      {sections.length > 0 && (
        <h2 className="section-h">
          {copy?.appearance_offers_heading ?? 'What people notice first'}
          <small>{copy?.appearance_offers_note ?? 'offered here'}</small>
        </h2>
      )}
      {sections.map((section) => (
        <ChapterOffers
          key={section.key}
          draft={draft}
          chapter="appearance"
          filter={(o) => o.opener_key === section.key}
          heading={section.label}
          headingTag={copy?.offers_chip_distinctions ?? 'Distinctions'}
          showOpener={false}
          syncErrorHint={copy?.offers_sync_error ?? 'That pick did not save. Try again.'}
          wordBundled={copy?.offers_word_bundled}
          wordPerRank={copy?.offers_word_per_rank}
          wordSpent={copy?.offers_word_spent}
          wordAwards={copy?.offers_word_awards}
          wordSeeMore={copy?.offers_word_see_more}
          wordHeld={copy?.offers_word_held}
          className="conditional"
        />
      ))}

      {draft.selected_species && (
        <>
          <h2 className="section-h">
            {copy?.appearance_features_heading ?? 'Physical features'}
            {hasQualities && (
              <small>
                {freeSpent} of {freePoints} feature points spent
              </small>
            )}
          </h2>
          {formOptionsLoading && (
            <p className="ledger-line" aria-busy="true">
              Loading physical features…
            </p>
          )}
          <div className="feature-grid">
            {(formOptions?.traits ?? []).map((t) => {
              const opened = openedTraits.has(t.trait.name);
              // What the feature offers without being distinctive: the species
              // palette and the lineage's own inherited options.
              const ordinary = [...t.options, ...inheritedOptionsFor(t.trait.id)];
              const ordinaryIds = new Set(ordinary.map((o) => o.id));
              return (
                <TraitBlock
                  key={t.trait.id}
                  draft={draft}
                  trait={t.trait}
                  // Distinctive, the feature reaches past that to every option the
                  // trait carries, the Unnatural umbrella included (#3739).
                  options={opened ? (t.all_options ?? ordinary) : ordinary}
                  ownIds={ordinaryIds}
                  opened={opened}
                  required={t.is_required}
                  selectedId={getSelectedOptionId(t.trait.name)}
                  onSelect={(optionId) => handleFormTraitChange(t.trait.name, optionId)}
                  descriptor={getTraitDescriptor(t.trait.name)}
                  onDescriptorCommit={(text) => handleTraitDescriptorCommit(t.trait.name, text)}
                  onClosed={() => handleTraitClosed(t.trait.name, ordinaryIds)}
                />
              );
            })}
            {strayInherited.map((group) => {
              const ids = new Set(group.options.map((o) => o.id));
              return (
                <TraitBlock
                  key={`${group.trait.id}-${group.source}`}
                  draft={draft}
                  trait={group.trait}
                  idSuffix={`-${group.source}`}
                  options={group.options}
                  ownIds={ids}
                  opened={openedTraits.has(group.trait.name)}
                  source={group.source}
                  selectedId={getSelectedOptionId(group.trait.name)}
                  onSelect={(optionId) => handleFormTraitChange(group.trait.name, optionId)}
                  descriptor={getTraitDescriptor(group.trait.name)}
                  onDescriptorCommit={(text) => handleTraitDescriptorCommit(group.trait.name, text)}
                  onClosed={() => handleTraitClosed(group.trait.name, ids)}
                />
              );
            })}
          </div>
        </>
      )}

      <h2 className="section-h">
        {copy?.appearance_description_heading ?? 'Physical description'}
      </h2>
      <Field id="description" label="Physical description">
        <textarea id="description" rows={6} {...register('description')} />
      </Field>

      <h2 className="section-h">{copy?.appearance_markings_heading ?? 'Markings'}</h2>
      <MarkingsEditor draft={draft} />
    </ChapterLeaf>
  );
}
