/**
 * Stage 7: Appearance (#3630).
 *
 * Physical characteristics as fields and choice rows: age and birthday day
 * and height in inches are typed numbers (a `StatRow`'s pips would run to a
 * hundred); birthday month, height band, build and each form trait are
 * pressed-row choices. The record rail lists the choices made so far; every
 * explanatory sentence the old layout put under a section heading now lives
 * in the margin instead (Decision 8).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { ChapterLeaf, ChoiceRow, Field, Marginalia, Note, RecordRail } from '../folio';
import {
  useBuilds,
  useCGExplanations,
  useFormOptions,
  useHeightBands,
  useUpdateDraft,
} from '../queries';
import { MarkingsEditor } from './MarkingsEditor';
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

const AGE_MIN = 18;
const AGE_MAX = 65;
// Eternal-youth species (elves, vampires) lock their apparent age in the
// early 20s (#2756) — mirrors the server-side cap.
const AGE_MAX_ETERNAL_YOUTH = 29;
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
  const { data: heightBands, isLoading: heightBandsLoading } = useHeightBands();
  const { data: builds, isLoading: buildsLoading } = useBuilds();
  const { data: formOptions, isLoading: formOptionsLoading } = useFormOptions(
    draft.selected_species?.id,
    draft.id
  );
  const draftData = draft.draft_data;

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
  // Eternal-youth species cap their age input (#2756); server enforces too.
  const ageMax = draft.selected_species?.eternal_youth ? AGE_MAX_ETERNAL_YOUTH : AGE_MAX;

  // Auto-save default age on first visit when unset, so backend sees age != None
  useEffect(() => {
    if (draft.age === null || draft.age === undefined) {
      updateDraft.mutate({ draftId: draft.id, data: { age: AGE_DEFAULT } });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.id]);

  const commitAge = () => {
    const parsed = parseInt(localAge, 10);
    const clamped = Number.isNaN(parsed)
      ? AGE_DEFAULT
      : Math.max(AGE_MIN, Math.min(ageMax, parsed));
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

  const heightBandTitle = (band: HeightBand): string =>
    !band.is_cg_selectable && isStaff
      ? `${band.min_inches} to ${band.max_inches} inches (not normally offered to players)`
      : `${band.min_inches} to ${band.max_inches} inches`;

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
                ? `${draft.height_band.display_name}, ${draft.height_inches} in`
                : undefined,
          },
          { label: 'Build', value: draft.build?.display_name },
        ]}
        ledger="Stage 8 of 11"
      />
      <Marginalia id="note-appearance">
        <Note lead="Age">
          Age must be between {AGE_MIN} and {ageMax} years.
        </Note>
        <Note lead="Birthday">
          The day your character celebrates each year. Friends will see it coming up in the Town
          Crier&apos;s tidings.
        </Note>
        <Note lead="Height">
          Select your height category, then fine-tune your exact height.
          {draft.height_band && (
            <>
              {' '}
              Other characters will see you as &quot;{draft.height_band.display_name}&quot; rather
              than your exact height.
            </>
          )}
        </Note>
        <Note lead="Build">Select your body type.</Note>
        {draft.selected_species && (
          <Note lead="Physical features">Select your character&apos;s physical features.</Note>
        )}
        <Note lead="Physical description">(Optional, appended to automatic descriptions)</Note>
        <Note lead="Markings">
          Tattoos, scars, brands, birthmarks — what your character&apos;s skin remembers. Clothing
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
            : copy?.appearance_age_hint
        }
      >
        <input
          id="age"
          type="number"
          min={AGE_MIN}
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
          hint={`${draft.height_band.min_inches} to ${draft.height_band.max_inches}`}
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
          {(formOptions?.traits ?? []).map((t) => (
            <div key={t.trait.id}>
              <h3 className="section-h" id={`trait-${t.trait.id}`}>
                {t.trait.display_name}
                {t.is_required && ' (required)'}
              </h3>
              <ChoiceRow
                labelledBy={`trait-${t.trait.id}`}
                label={t.trait.display_name}
                options={[...t.options, ...inheritedOptionsFor(t.trait.id)].map((o) => ({
                  value: o.id,
                  label: o.display_name,
                }))}
                value={getSelectedOptionId(t.trait.name)}
                onChange={(optionId) => handleFormTraitChange(t.trait.name, optionId)}
                clearable={!t.is_required}
              />
              <Field id={`desc-${t.trait.id}`} label="In your own words" hint="Optional.">
                <input
                  id={`desc-${t.trait.id}`}
                  type="text"
                  defaultValue={getTraitDescriptor(t.trait.name)}
                  onBlur={(e) => handleTraitDescriptorCommit(t.trait.name, e.target.value)}
                />
              </Field>
            </div>
          ))}
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
              <Field
                id={`desc-${group.trait.id}-${group.source}`}
                label="In your own words"
                hint="Optional."
              >
                <input
                  id={`desc-${group.trait.id}-${group.source}`}
                  type="text"
                  defaultValue={getTraitDescriptor(group.trait.name)}
                  onBlur={(e) => handleTraitDescriptorCommit(group.trait.name, e.target.value)}
                />
              </Field>
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
      <MarkingsEditor draftId={draft.id} />
    </ChapterLeaf>
  );
}
