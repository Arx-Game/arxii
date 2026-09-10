/**
 * Stage 7: Appearance (#3630).
 *
 * Physical characteristics as fields and choice rows: age and birthday day
 * and height in inches are typed numbers (a `StatRow`'s pips would run to a
 * hundred); birthday month, height band, build and each form trait are
 * pressed-row choices. The record rail lists the choices made so far; every
 * explanatory sentence the old layout put under a section heading now lives
 * in the margin instead (Decision 8).
 *
 * Right after the height block, `ChapterOffers` mounts this chapter's own
 * offered distinctions (`chapter="appearance"`, #3675 Task 15) - the
 * physical/social ones that show, in place of the retired Distinctions
 * stage. It carries its own heading (folio grammar; no separate `section-h`
 * above it, matching the demo's Screen 7). A height band's `title` reads its
 * own `cg_hint` column when staff authored one (fix round 1: an authored
 * column on the row itself, the #3676 one-to-one designation, not a name
 * match against a literal "Towering"); otherwise the usual inches range.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import {
  ChapterLeaf,
  ChoiceRow,
  Field,
  Marginalia,
  Note,
  RecordRail,
  stageEyebrow,
} from '../folio';
import {
  useBuilds,
  useCGExplanations,
  useDraftOffers,
  useFormOptions,
  useHeightBands,
  useUpdateDraft,
} from '../queries';
import { formatHeight } from '../utils';
import { ChapterOffers } from './offers/ChapterOffers';
import { FeatureDistinctions } from './offers/FeatureDistinctions';
import { MarkingsEditor } from './MarkingsEditor';
import { useDraftDistinctions } from '@/hooks/useDistinctions';
import { Stage } from '../types';
import type { Build, CharacterDraft, FormTraitOption, HeightBand } from '../types';

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

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];
// 29 for February: leap-day birthdays are legal (#2756).
const DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

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
      // A per-feature line (#3739) is not a section: it is offered on every
      // trait row and marking, and `FeatureDistinctions` mounts it there.
      if (offer.taken_per_feature) continue;
      if (offer.opener_key && !seen.has(offer.opener_key)) {
        seen.set(offer.opener_key, offer.opener_label);
      }
    }
    return Array.from(seen, ([key, label]) => ({ key, label }));
  }, [appearanceOffers]);
  const hasClosedAppearance = (appearanceOffers?.closed ?? []).length > 0;
  const { data: heightBands, isLoading: heightBandsLoading } = useHeightBands();
  const { data: builds, isLoading: buildsLoading } = useBuilds();
  const { data: formOptions, isLoading: formOptionsLoading } = useFormOptions(
    draft.selected_species?.id,
    draft.id
  );
  const draftData = draft.draft_data;
  // Which trait rows the draft has paid to make distinctive (#3739). The unlock
  // is what opens the widened palette and the description field, so the leaf
  // reads it from the draft's own entries rather than re-deriving the rule.
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const openedTraits = useMemo(() => {
    const opensIds = new Set(
      (appearanceOffers?.offers ?? []).filter((o) => o.opens_feature).map((o) => o.distinction_id)
    );
    return new Set(
      (draftDistinctions ?? [])
        .filter((e) => opensIds.has(e.distinction_id) && e.feature_trait)
        .map((e) => e.feature_trait as string)
    );
  }, [appearanceOffers, draftDistinctions]);

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
    const parsed = parseInt(localAge, 10);
    const clamped = Number.isNaN(parsed) ? AGE_DEFAULT : Math.max(ageMin, Math.min(ageMax, parsed));
    setLocalAge(String(clamped));
    if (clamped !== draft.age) {
      updateDraft.mutate({
        draftId: draft.id,
        data: { age: clamped },
      });
    }
  };

  // Celebrated birthday (#2756) — waking day for Sleeper beginnings.
  const birthdayMonth = draft.birthday_month;
  const birthdayDay = draft.birthday_day;
  const maxDay = birthdayMonth ? DAYS_IN_MONTH[birthdayMonth - 1] : 31;

  const commitBirthday = (month: number | null, day: number | null) => {
    const clampedDay =
      month !== null && day !== null ? Math.max(1, Math.min(DAYS_IN_MONTH[month - 1], day)) : day;
    updateDraft.mutate({
      draftId: draft.id,
      data: { birthday_month: month, birthday_day: clampedDay },
    });
  };

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
    const parsed = parseInt(heightInput ?? '', 10);
    if (!Number.isNaN(parsed)) {
      const clamped = Math.max(band.min_inches, Math.min(band.max_inches, parsed));
      if (clamped !== draft.height_inches) {
        updateDraft.mutate({
          draftId: draft.id,
          data: { height_inches: clamped },
        });
      }
    }
    setHeightInput(null);
  };

  const handleBuildSelect = (build: Build) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { build_id: build.id },
    });
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

  // #2632 — optional per-trait flavor text ("red" + "flowing crimson"). The
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

  // A band's title is its own authored `cg_hint` (#3675 Task 15 fix round
  // 1) when staff wrote one - what opens a band players cannot normally
  // take (e.g. Towering needs Giant's Blood). This is a column on the row
  // itself, not a name match against a literal band name (the #3676
  // one-to-one designation the never-match-strings ruling asks for).
  // Absent a hint, the option falls back to the usual inches range.
  const heightBandTitle = (band: HeightBand): string | undefined =>
    band.cg_hint ||
    (!band.is_cg_selectable && isStaff
      ? `${band.min_inches} to ${band.max_inches} inches (not normally offered to players)`
      : `${band.min_inches} to ${band.max_inches} inches`);

  const buildTitle = (build: Build): string | undefined =>
    !build.is_cg_selectable && isStaff ? 'Not normally offered to players' : undefined;

  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Species', value: draft.selected_species?.name },
          { label: 'Age', value: draft.age !== null ? String(draft.age) : undefined },
          {
            label: 'Height',
            value:
              draft.height_band && draft.height_inches !== null
                ? `${draft.height_band.display_name}, ${formatHeight(draft.height_inches)}`
                : undefined,
          },
          { label: 'Build', value: draft.build?.display_name },
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

  return (
    <ChapterLeaf
      stage={Stage.APPEARANCE}
      title={copy?.appearance_heading ?? 'Appearance'}
      intro={copy?.appearance_intro}
      aside={rail}
    >
      <h2 className="section-h">{copy?.appearance_age_heading ?? 'Age'}</h2>
      <Field
        id="age"
        label="Age"
        hint={
          draft.selected_species?.eternal_youth
            ? 'Your species keeps its eternal youth; apparent age locks in the early twenties.'
            : // Unseeded copy key today; renders nothing until staff write it.
              copy?.appearance_age_hint
        }
      >
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

      <h2 className="section-h">{copy?.appearance_birthday_heading ?? 'Birthday'}</h2>
      <ChoiceRow
        label="Month"
        options={MONTH_NAMES.map((name, index) => ({ value: index + 1, label: name }))}
        value={birthdayMonth}
        onChange={(month) => commitBirthday(month, birthdayDay ?? 1)}
      />
      <Field id="bday" label="Day">
        <input
          id="bday"
          type="number"
          min={1}
          max={maxDay}
          value={birthdayDay ?? ''}
          onChange={(e) => {
            const parsed = parseInt(e.target.value, 10);
            if (!Number.isNaN(parsed) && birthdayMonth) {
              commitBirthday(birthdayMonth, parsed);
            }
          }}
          disabled={!birthdayMonth}
        />
      </Field>

      <h2 className="section-h">{copy?.appearance_height_heading ?? 'Height'}</h2>
      {heightBandsLoading ? (
        <p className="ledger-line" aria-busy="true">
          Loading height bands…
        </p>
      ) : (
        <ChoiceRow
          label="Height band"
          options={(heightBands ?? []).map((band) => ({
            value: band.id,
            label: band.display_name,
            title: heightBandTitle(band),
          }))}
          value={draft.height_band?.id ?? null}
          onChange={(id) => {
            const band = (heightBands ?? []).find((b) => b.id === id);
            if (band) handleHeightBandSelect(band);
          }}
        />
      )}
      {draft.height_band && (
        <Field
          id="height"
          label="Height in inches"
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

      {/* What shows, in sections (#3709): one offers block per authored Appearance
          section, in the sections' own order; the closed hint prints once under the
          last. The chapter heading stays even when only the closed hint remains. */}
      {(sections.length > 0 || hasClosedAppearance) && (
        <h2 className="section-h">
          {copy?.appearance_offers_heading ?? 'What people notice first'}
          <small>{copy?.appearance_offers_note ?? 'offered here'}</small>
        </h2>
      )}
      {sections.map((section, index) => (
        <ChapterOffers
          key={section.key}
          draft={draft}
          chapter="appearance"
          filter={(o) => o.opener_key === section.key}
          heading={section.label}
          headingTag={copy?.offers_chip_distinctions ?? 'Distinctions'}
          showOpener={false}
          showClosed={index === sections.length - 1}
          closedLead={copy?.appearance_closed_lead ?? 'Closed by your route'}
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
      {sections.length === 0 && hasClosedAppearance && (
        <ChapterOffers
          draft={draft}
          chapter="appearance"
          filter={() => false}
          closedLead={copy?.appearance_closed_lead ?? 'Closed by your route'}
        />
      )}

      <h2 className="section-h">{copy?.appearance_build_heading ?? 'Build'}</h2>
      {buildsLoading ? (
        <p className="ledger-line" aria-busy="true">
          Loading builds…
        </p>
      ) : (
        <ChoiceRow
          label="Build"
          options={(builds ?? []).map((build) => ({
            value: build.id,
            label: build.display_name,
            title: buildTitle(build),
          }))}
          value={draft.build?.id ?? null}
          onChange={(id) => {
            const build = (builds ?? []).find((b) => b.id === id);
            if (build) handleBuildSelect(build);
          }}
        />
      )}

      {draft.selected_species && (
        <>
          <h2 className="section-h">{copy?.appearance_features_heading ?? 'Physical features'}</h2>
          {formOptionsLoading && (
            <p className="ledger-line" aria-busy="true">
              Loading physical features…
            </p>
          )}
          {(formOptions?.traits ?? []).map((t) => {
            const opened = openedTraits.has(t.trait.name);
            // Made distinctive, the row reaches past the species palette to
            // every option the trait carries, the Unnatural umbrella included
            // (#3739); otherwise it offers the palette and the lineage's own
            // inherited options, exactly as before.
            const palette = opened
              ? (t.all_options ?? t.options)
              : [...t.options, ...inheritedOptionsFor(t.trait.id)];
            // Which of those the species does not itself list: drawn apart, so the
            // point the player spent is visible in the row it opened (#3739).
            const ownIds = new Set(t.options.map((o) => o.id));
            return (
              <div key={t.trait.id}>
                <h3 className="section-h" id={`trait-${t.trait.id}`}>
                  {t.trait.display_name}
                  {t.is_required && ' (required)'}
                </h3>
                <ChoiceRow
                  labelledBy={`trait-${t.trait.id}`}
                  label={t.trait.display_name}
                  options={palette.map((o) => ({
                    value: o.id,
                    label: o.display_name,
                    beyond: opened && !ownIds.has(o.id),
                  }))}
                  value={getSelectedOptionId(t.trait.name)}
                  onChange={(optionId) => handleFormTraitChange(t.trait.name, optionId)}
                  clearable={!t.is_required}
                />
                <FeatureDistinctions
                  draft={draft}
                  feature={{ feature_trait: t.trait.name }}
                  featureLabel={t.trait.display_name}
                  unlockLabel={copy?.appearance_make_distinctive}
                  unlockWhy={copy?.appearance_make_distinctive_why}
                  perTierWord={copy?.appearance_per_tier}
                />
                {opened && (
                  <Field id={`desc-${t.trait.id}`} label="Describe it" hint="Optional.">
                    <input
                      id={`desc-${t.trait.id}`}
                      type="text"
                      maxLength={120}
                      defaultValue={getTraitDescriptor(t.trait.name)}
                      onBlur={(e) => handleTraitDescriptorCommit(t.trait.name, e.target.value)}
                    />
                  </Field>
                )}
              </div>
            );
          })}
          {strayInherited.map((group) => (
            <div key={`${group.trait.id}-${group.source}`}>
              <h3 className="section-h" id={`trait-${group.trait.id}-${group.source}`}>
                {group.trait.display_name}{' '}
                <span className="entry-gloss">(from {group.source})</span>
              </h3>
              <ChoiceRow
                labelledBy={`trait-${group.trait.id}-${group.source}`}
                label={group.trait.display_name}
                options={group.options.map((o) => ({ value: o.id, label: o.display_name }))}
                value={getSelectedOptionId(group.trait.name)}
                onChange={(optionId) => handleFormTraitChange(group.trait.name, optionId)}
                clearable
              />
              <FeatureDistinctions
                draft={draft}
                feature={{ feature_trait: group.trait.name }}
                featureLabel={group.trait.display_name}
                unlockLabel={copy?.appearance_make_distinctive}
                unlockWhy={copy?.appearance_make_distinctive_why}
                perTierWord={copy?.appearance_per_tier}
              />
              {openedTraits.has(group.trait.name) && (
                <Field
                  id={`desc-${group.trait.id}-${group.source}`}
                  label="Describe it"
                  hint="Optional."
                >
                  <input
                    id={`desc-${group.trait.id}-${group.source}`}
                    type="text"
                    maxLength={120}
                    defaultValue={getTraitDescriptor(group.trait.name)}
                    onBlur={(e) => handleTraitDescriptorCommit(group.trait.name, e.target.value)}
                  />
                </Field>
              )}
            </div>
          ))}
        </>
      )}

      <h2 className="section-h">
        {copy?.appearance_description_heading ?? 'Physical description'}
      </h2>
      <Field id="description" label="Physical description">
        <textarea id="description" rows={6} {...register('description')} />
      </Field>

      <h2 className="section-h">{copy?.appearance_markings_heading ?? 'Markings'}</h2>
      <MarkingsEditor
        draft={draft}
        markingUnlockLabel={copy?.appearance_make_distinctive}
        markingUnlockWhy={copy?.appearance_marking_distinctive_why}
        perTierWord={copy?.appearance_per_tier}
      />
    </ChapterLeaf>
  );
}
