/**
 * Stage 6: Gift (#3630).
 *
 * The Gift funnel (Tradition, Gift, Techniques, Resonance, fighting style (#4921, only
 * for a Tradition that teaches one), magical training (#4659, only for a draft with
 * training; after the Resonance, whose affinity its bonus reads, and the style, whose
 * skill it lists), Anima Check) as nested index entries: each step is an `Entry` in an `EntryList`,
 * closed and unreadable (`gated`) until the step before it is done, and its
 * own body holds that step's picker. Motif is a field below the funnel;
 * the Glimpse is mounted via `GlimpseSection` (#2427; folio-grammar
 * `GlimpseAxes` layout, #3675 fix round 1); GiftStage's own `section-h`
 * above it carries the chapter heading, `GlimpseSection` renders no
 * heading of its own. The record rail lists the choices made so far
 * (including one row per Glimpse-offer draft entry, fix round 1); it
 * explains nothing (Decision 8).
 */

import { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import type { ReactNode } from 'react';
import { useDraftDistinctions } from '@/hooks/useDistinctions';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import {
  ChapterLeaf,
  Entry,
  EntryList,
  Field,
  Marginalia,
  Note,
  RecordRail,
  stageEyebrow,
} from '../folio';
import {
  useCGExplanations,
  useCGCombatStyles,
  useCGGifts,
  useDraftOffers,
  useGlimpseTags,
  useAffinities,
  useResonances,
  useSkills,
  useStatDefinitions,
  useUpdateDraft,
} from '../queries';
import { useShownPicks } from '../useShownPicks';
import type {
  CGExplanations,
  CharacterDraft,
  GlimpseCard,
  GlimpseMemory,
  GlimpseTagOption,
  ResonanceWeightPick,
  Tradition,
} from '../types';
import { capitalize, countNoun } from '../utils';
import { Stage } from '../types';
import { AnimaCheckStep } from './gift/AnimaCheckStep';
import { GiftFacetsField } from './gift/GiftFacetsField';
import { GiftSelector } from './gift/GiftSelector';
import { AXIS_STEPS } from '@/magic/components/glimpse/GlimpseFlow';
import type { GlimpseAxisStep } from '@/magic/components/glimpse/glimpseTypes';
import { GlimpseSection } from './gift/GlimpseSection';
import { AXIS_DISPLAY_NAME, draftGlimpseMemory } from './gift/glimpseParts';
import { MagicTrainingBlock } from './gift/MagicTrainingBlock';
import { StrengthStep } from './gift/StrengthStep';
import { StyleStep } from './gift/StyleStep';
import { heaviestFirst, leadResonanceId, strengthPicksComplete } from '../resonanceWeights';
import { hasMagicTraining, isTrainingSpent, trainingHeading } from './gift/magicTraining';
import { TechniqueSelector } from './gift/TechniqueSelector';
import { TraditionStep } from './gift/TraditionStep';
import { cgRecord } from '../cgRecord';

interface GiftStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => void;
}

export interface GiftFormValues {
  anima_ritual_name: string;
  motif_description: string;
  glimpse_story: string;
}

interface FunnelStepProps {
  n: number;
  total: number;
  name: string;
  value?: string;
  done: boolean;
  gated: boolean;
  gateReason: string;
  open: boolean;
  children: ReactNode;
}

/** One step of the Gift funnel: readable once the step before it is done,
 * choosable only then — its body (the step's own picker) mounts only when
 * unlocked, so a gated step never fires the queries its picker would make. */
function FunnelStep({
  n,
  total,
  name,
  value,
  done,
  gated,
  gateReason,
  open,
  children,
}: FunnelStepProps) {
  return (
    <Entry
      name={name}
      gloss={value ?? undefined}
      tag={gated ? gateReason : `Step ${n} of ${total}`}
      chosen={done}
      closed={gated}
      open={open}
    >
      {!gated && children}
    </Entry>
  );
}

/**
 * The name of the schooling stance the draft currently holds under a chosen
 * tradition, if any: the draft entry whose `offer_ids` include one of the
 * tradition's schooling offers, mapped back to that row's name (same lookup
 * `SchoolingStances` itself uses to find its own current pick, #3675).
 */
function schoolingPickName(
  tradition: Tradition | null,
  entries: DraftDistinctionEntry[] | undefined
): string | undefined {
  if (!tradition) return undefined;
  const offerIds = new Set(
    tradition.schooling.map((row) => row.offer_id).filter((id): id is number => id != null)
  );
  const entry = (entries ?? []).find((e) =>
    e.offer_ids.some((id) => typeof id === 'number' && offerIds.has(id))
  );
  if (!entry) return undefined;
  return tradition.schooling.find(
    (row) => row.offer_id != null && entry.offer_ids.includes(row.offer_id)
  )?.name;
}

/**
 * The Glimpse's rows in the side panel (#5292): one row for each part that gives a
 * card, then one for the card that marks a blackout or no memory.
 *
 * A part's row reads the card its answer gave, "no card" for an answer that gives
 * none, nothing (the panel's own "not yet chosen") for a part with no answer, and
 * "not asked" for a part the memory state leaves out. No price: a Glimpse card is
 * free and the CG points never move because of it.
 *
 * The cards are the server's list of what the Glimpse gave the draft (`glimpse_cards`
 * on the chapter's offers). While that list is being fetched again after a click, the
 * card printed on the answer itself (the catalogue's) stands in, so the row does not
 * read "no card" for the length of a request.
 */
function glimpseRailRows(
  memory: GlimpseMemory,
  answers: GlimpseTagOption[],
  cards: GlimpseCard[] | undefined,
  isRefreshing: boolean,
  copy: CGExplanations | undefined
): { label: string; value: string | undefined }[] {
  const asked = (step: GlimpseAxisStep) =>
    memory === 'remembered' || (memory === 'blacked_out' && !step.lostInBlackout);
  const rows: { label: string; value: string | undefined }[] = [];
  for (const step of AXIS_STEPS.filter((candidate) => candidate.givesCard)) {
    const label =
      copy?.[`glimpse_axis_${step.axis.toLowerCase()}_chip`] ?? AXIS_DISPLAY_NAME[step.axis];
    if (!asked(step)) {
      rows.push({ label, value: copy?.glimpse_rail_not_asked ?? 'not asked' });
      continue;
    }
    const answer = answers.find((tag) => tag.axis === step.axis);
    if (!answer) {
      rows.push({ label, value: undefined });
      continue;
    }
    const given = cards?.find((card) => card.axis === step.axis)?.name;
    const card = given ?? (isRefreshing || !cards ? answer.offers[0]?.name : undefined);
    rows.push({ label, value: card ?? copy?.glimpse_rail_no_card ?? 'no card' });
  }
  for (const marker of (cards ?? []).filter((card) => card.axis === '')) {
    rows.push({ label: marker.name, value: copy?.glimpse_rail_held ?? 'held' });
  }
  return rows;
}

interface LaterStepsInput {
  showStyle: boolean;
  showTraining: boolean;
  styleChosen: boolean;
  giftDone: boolean;
  resonanceDone: boolean;
  /** What the Resonance step still waits on, worded for the step it gates. */
  resonanceGate: string;
}

/**
 * The steps after the Resonance (#4921): the style step (only for a Tradition that
 * teaches one), the training (only with training) and the Anima Check, numbered in that
 * order, and whether the training is open yet and what it waits on if not.
 */
function laterSteps({
  showStyle,
  showTraining,
  styleChosen,
  giftDone,
  resonanceDone,
  resonanceGate,
}: LaterStepsInput) {
  const styleNumber = 5;
  const trainingNumber = styleNumber + (showStyle ? 1 : 0);
  const animaNumber = trainingNumber + (showTraining ? 1 : 0);
  const trainingReady = giftDone && resonanceDone && (!showStyle || styleChosen);
  let trainingGate = 'Choose a style first';
  if (!giftDone) trainingGate = 'Choose a gift first';
  else if (!resonanceDone) trainingGate = resonanceGate;
  return {
    styleNumber,
    trainingNumber,
    animaNumber,
    stepCount: animaNumber,
    trainingReady,
    trainingGate,
  };
}

export function GiftStage({ draft, onRegisterBeforeLeave }: GiftStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: resonances = [] } = useResonances();
  const { data: affinities = [] } = useAffinities();
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);

  const draftData = draft.draft_data;
  const giftId = draftData.selected_gift_id ?? null;
  const resonanceWeights = draftData.gift_resonance_weights ?? [];
  const creationPoints = draft.resonance_creation_points;
  const selectedTechniqueIds = draftData.selected_technique_ids ?? [];
  const picks = draft.starting_technique_picks;

  const completion = {
    tradition: draft.selected_tradition != null,
    gift: giftId != null,
    techniques: selectedTechniqueIds.length > 0,
    // The step is done only when the picks obey the rule: one feeling, at most one second
    // pick, every creation point placed (#5231). A draft saved under the old rule is not.
    resonance: strengthPicksComplete(resonanceWeights, resonances, creationPoints),
    anima: draftData.anima_check_stat_id != null && draftData.anima_check_skill_id != null,
  };

  // The Gift step's rail/gloss value needs the gift's name, which the draft
  // only carries as an id — read the same catalog GiftSelector fetches,
  // gated on a tradition being chosen so it never fires before GiftSelector
  // itself would (and never races the unmocked network in a test that never
  // selects a tradition).
  const { data: cgGifts } = useCGGifts(
    completion.tradition ? draft.id : undefined,
    draft.selected_path?.id,
    draft.selected_tradition?.id
  );
  const giftName = cgGifts?.find((gift) => gift.id === giftId)?.name;
  // The picks heaviest first: the step's gloss and the rail name them all, and the facets
  // below belong to the heaviest.
  const pickedNames = heaviestFirst(resonanceWeights)
    .map((pick) => resonances.find((r) => r.id === pick.resonance_id)?.name)
    .filter((name): name is string => name != null);
  const resonanceName = pickedNames.length > 0 ? pickedNames.join(', ') : undefined;
  const leadResonanceName = resonances.find(
    (r) => r.id === leadResonanceId(resonanceWeights)
  )?.name;
  const resonanceGate = 'Choose a resonance first';
  const techniqueCountLine = `${selectedTechniqueIds.length} of ${picks} chosen`;

  // Magical training (#4659) is its own step after the Resonance: its fit bonuses count
  // the Gift and the resonance's affinity, so it opens only once both are picked. It
  // exists only for a draft with training (or a stale allocation) and stays open until
  // the allocation spends exactly what it must.
  const training = draft.magic_training;
  const showTraining = hasMagicTraining(training);
  const trainingSpent = showTraining && isTrainingSpent(training);

  // The style step (#4921) sits after the Resonance, only for a Tradition that teaches a
  // style; the training after it waits on the style, since its list holds the style's skill.
  const { data: styles = [] } = useCGCombatStyles(draft.id, draft.selected_tradition?.id ?? null);
  const showStyle = styles.length > 0;
  const chosenStyle = styles.find((style) => style.id === draft.selected_combat_style);
  const { styleNumber, trainingNumber, animaNumber, stepCount, trainingReady, trainingGate } =
    laterSteps({
      showStyle,
      showTraining,
      styleChosen: chosenStyle != null,
      giftDone: completion.gift,
      resonanceDone: completion.resonance,
      resonanceGate,
    });
  const trainingValue = showTraining ? `${training.allocated} of ${training.total}` : undefined;

  // The Tradition row names the schooling stance under it, when one is
  // picked (the tradition step's own SchoolingStances, #3675): the same "How
  // you came to it" line the tradition step itself asks.
  const schoolingName = schoolingPickName(draft.selected_tradition, draftDistinctions);
  const traditionValue = draft.selected_tradition
    ? [draft.selected_tradition.name, schoolingName].filter(Boolean).join(' · ')
    : undefined;

  // The Glimpse's rows (#5292): the card each part's answer gave, from the chapter's
  // own list of what the Glimpse gave this draft. The answers are read from the draft,
  // so a click shows at once.
  const { data: glimpseOffersData, isFetching: glimpseCardsRefreshing } = useDraftOffers(
    draft.id,
    'glimpse'
  );
  const { data: glimpseTags } = useGlimpseTags(draft.selected_path?.id);
  const glimpseAnswerIds = new Set(draft.draft_data.glimpse_tag_ids ?? []);
  const glimpseRows = glimpseRailRows(
    draftGlimpseMemory(draft),
    (glimpseTags ?? []).filter((tag) => glimpseAnswerIds.has(tag.id)),
    glimpseOffersData?.glimpse_cards,
    glimpseCardsRefreshing,
    copy
  );

  const shownPoints = useShownPicks(draft);
  const record = cgRecord(draft, { tradition: traditionValue, points: shownPoints });

  // The Anima Check step's gloss and rail row need the names behind the two
  // ids the draft stores, so read the same two catalogs AnimaCheckStep picks
  // from. The step itself only mounts once unlocked; these lines have to read
  // as a chosen value while it is closed.
  const { data: statDefinitions } = useStatDefinitions();
  const { data: skills } = useSkills();
  const animaStatName = statDefinitions?.find(
    (stat) => stat.id === draftData.anima_check_stat_id
  )?.name;
  const animaSkillName = skills?.find((skill) => skill.id === draftData.anima_check_skill_id)?.name;
  const animaCheckLine =
    animaStatName && animaSkillName
      ? `${capitalize(animaStatName)} + ${animaSkillName}`
      : undefined;

  // The step stays open once the player has picked in it this visit, even though one feeling
  // alone completes it: its second question, slider and aura are still in front of her. A draft
  // that arrives complete shows it folded, like every finished step.
  const [resonancePicked, setResonancePicked] = useState(false);

  const handleResonanceWeights = (weights: ResonanceWeightPick[]) => {
    setResonancePicked(true);
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { gift_resonance_weights: weights } },
    });
  };

  const { register, getValues, formState } = useForm<GiftFormValues>({
    defaultValues: {
      anima_ritual_name: draftData.anima_ritual_name ?? '',
      motif_description: draftData.motif_description ?? '',
      glimpse_story: draftData.glimpse_story ?? '',
    },
  });

  const saveFormFields = useCallback(async () => {
    if (!formState.isDirty) return true;
    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: {
          draft_data: {
            ...getValues(),
          },
        },
      });
      return true;
    } catch {
      return window.confirm('Failed to save. Discard changes and continue?');
    }
  }, [draft.id, updateDraft, formState.isDirty, getValues]);

  useEffect(() => {
    if (onRegisterBeforeLeave) {
      onRegisterBeforeLeave(saveFormFields);
    }
  }, [onRegisterBeforeLeave, saveFormFields]);

  const rail = (
    <>
      <RecordRail
        rows={[
          ...record.head,
          { label: 'Gift', value: giftName },
          { label: 'Techniques', value: completion.gift ? techniqueCountLine : undefined },
          { label: 'Resonance', value: resonanceName },
          ...(showStyle ? [{ label: 'Style', value: chosenStyle?.name }] : []),
          { label: 'Anima check', value: animaCheckLine },
          ...glimpseRows,
          record.points,
        ]}
        ledger={stageEyebrow(draft.current_stage)}
      />
      <Marginalia id="note-gift">
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Techniques">
          are capped at {countNoun(picks, 'pick')} at this stage; the budget comes from your
          distinctions.
        </Note>
      </Marginalia>
    </>
  );

  return (
    <ChapterLeaf
      stage={Stage.GIFT}
      title={copy?.magic_heading ?? 'Magic & Gifts'}
      intro={copy?.magic_intro}
      aside={rail}
    >
      {copy?.gift_lore_intro && (
        <div className="leaf-body">
          <p>{copy.gift_lore_intro}</p>
        </div>
      )}

      <EntryList label="Gift steps">
        <FunnelStep
          n={1}
          total={stepCount}
          name={copy?.gift_tradition_heading ?? 'Tradition'}
          value={draft.selected_tradition?.name}
          done={completion.tradition}
          gated={false}
          gateReason=""
          open={!completion.tradition}
        >
          <TraditionStep draft={draft} />
        </FunnelStep>

        <FunnelStep
          n={2}
          total={stepCount}
          name="Gift"
          value={giftName}
          done={completion.gift}
          gated={!completion.tradition}
          gateReason="Choose a tradition first"
          open={completion.tradition && !completion.gift}
        >
          <GiftSelector draft={draft} />
        </FunnelStep>

        <FunnelStep
          n={3}
          total={stepCount}
          name="Techniques"
          value={completion.gift ? techniqueCountLine : undefined}
          done={completion.techniques}
          gated={!completion.gift}
          gateReason="Choose a gift first"
          open={completion.gift && !completion.techniques}
        >
          {giftId != null && <TechniqueSelector draft={draft} giftId={giftId} />}
        </FunnelStep>

        <FunnelStep
          n={4}
          total={stepCount}
          name="Your Resonance"
          value={resonanceName}
          done={completion.resonance}
          gated={!completion.techniques}
          gateReason="Choose your techniques first"
          open={completion.techniques && (!completion.resonance || resonancePicked)}
        >
          <StrengthStep
            resonances={resonances}
            affinities={affinities}
            weights={resonanceWeights}
            budget={creationPoints}
            copy={copy}
            onChange={handleResonanceWeights}
          />
        </FunnelStep>

        {showStyle && (
          <FunnelStep
            n={styleNumber}
            total={stepCount}
            name="Fighting style"
            value={chosenStyle?.name}
            done={chosenStyle != null}
            gated={!completion.resonance}
            gateReason={resonanceGate}
            open={completion.resonance && chosenStyle == null}
          >
            <StyleStep draft={draft} styles={styles} />
          </FunnelStep>
        )}

        {showTraining && (
          <FunnelStep
            n={trainingNumber}
            total={stepCount}
            name={trainingHeading(copy, draft.selected_tradition?.name ?? '')}
            value={trainingValue}
            done={trainingSpent}
            gated={!trainingReady}
            gateReason={trainingGate}
            open={trainingReady && !trainingSpent}
          >
            <MagicTrainingBlock draft={draft} />
          </FunnelStep>
        )}

        <FunnelStep
          n={animaNumber}
          total={stepCount}
          name={copy?.anima_check_heading ?? 'Anima Check'}
          value={animaCheckLine}
          done={completion.anima}
          gated={!completion.resonance}
          gateReason={resonanceGate}
          open={completion.resonance && !completion.anima}
        >
          <AnimaCheckStep draft={draft} register={register} />
        </FunnelStep>
      </EntryList>

      <h2 className="section-h" id="motif-heading">
        {copy?.magic_motif_heading ?? 'Motif'}
      </h2>
      <Field id="motif" label="Motif" hint={copy?.magic_motif_desc}>
        <textarea id="motif" rows={4} {...register('motif_description')} />
      </Field>
      <GiftFacetsField draft={draft} resonanceName={leadResonanceName} />

      <h2 className="section-h" id="glimpse-heading">
        {copy?.magic_glimpse_heading ?? 'The Glimpse'}
      </h2>
      <GlimpseSection draft={draft} glimpseProseField={register('glimpse_story')} />
    </ChapterLeaf>
  );
}
