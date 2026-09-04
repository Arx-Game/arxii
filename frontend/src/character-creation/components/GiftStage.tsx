/**
 * Stage 6: Gift (#3630).
 *
 * The five-step Gift funnel — Tradition, Gift, Techniques, Resonance, Anima
 * Check — as nested index entries: each step is an `Entry` in an `EntryList`,
 * closed and unreadable (`gated`) until the step before it is done, and its
 * own body holds that step's picker. Motif is a field below the funnel;
 * the Glimpse is the guided tag-driven flow mounted via `GlimpseSection`
 * (#2427), unchanged. The record rail lists the choices made so far; it
 * explains nothing (Decision 8).
 */

import { useCallback, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import type { ReactNode } from 'react';
import {
  ChapterLeaf,
  CodexLine,
  Entry,
  EntryDoors,
  EntryList,
  Field,
  Marginalia,
  Note,
  RecordRail,
} from '../folio';
import {
  useCGExplanations,
  useCGGifts,
  useResonances,
  useSkills,
  useStatDefinitions,
  useUpdateDraft,
} from '../queries';
import type { CharacterDraft } from '../types';
import { Stage } from '../types';
import { AnimaCheckStep } from './gift/AnimaCheckStep';
import { GiftSelector } from './gift/GiftSelector';
import { GlimpseSection } from './gift/GlimpseSection';
import { TechniqueSelector } from './gift/TechniqueSelector';
import { TraditionStep } from './gift/TraditionStep';

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
function FunnelStep({ n, name, value, done, gated, gateReason, open, children }: FunnelStepProps) {
  return (
    <Entry
      name={name}
      gloss={value ?? undefined}
      tag={gated ? gateReason : `Step ${n} of 5`}
      chosen={done}
      closed={gated}
      open={open}
    >
      {!gated && children}
    </Entry>
  );
}

export function GiftStage({ draft, onRegisterBeforeLeave }: GiftStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: resonances = [] } = useResonances();

  const draftData = draft.draft_data;
  const giftId = draftData.selected_gift_id ?? null;
  const selectedResonanceId = draftData.selected_gift_resonance_id ?? null;
  const selectedTechniqueIds = draftData.selected_technique_ids ?? [];
  const picks = draft.starting_technique_picks;

  const completion = {
    tradition: draft.selected_tradition != null,
    gift: giftId != null,
    techniques: selectedTechniqueIds.length > 0,
    resonance: selectedResonanceId != null,
    anima: draftData.anima_check_stat_id != null && draftData.anima_check_skill_id != null,
  };

  // The Gift step's rail/gloss value needs the gift's name, which the draft
  // only carries as an id — read the same catalog GiftSelector fetches,
  // gated on a tradition being chosen so it never fires before GiftSelector
  // itself would (and never races the unmocked network in a test that never
  // selects a tradition).
  const { data: cgGifts } = useCGGifts(completion.tradition ? draft.id : undefined);
  const giftName = cgGifts?.find((gift) => gift.id === giftId)?.name;
  const resonanceName = resonances.find((r) => r.id === selectedResonanceId)?.name;
  const techniqueCountLine = `${selectedTechniqueIds.length} of ${picks} chosen`;

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
    animaStatName && animaSkillName ? `${animaStatName} + ${animaSkillName}` : undefined;

  const handleSelectResonance = (resonanceId: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          selected_gift_resonance_id: resonanceId,
        },
      },
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
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Beginnings', value: draft.selected_beginnings?.name },
          { label: 'Species', value: draft.selected_species?.name },
          { label: 'Path', value: draft.selected_path?.name },
          { label: 'Tradition', value: draft.selected_tradition?.name },
          { label: 'Gift', value: giftName },
          { label: 'Techniques', value: completion.gift ? techniqueCountLine : undefined },
          { label: 'Resonance', value: resonanceName },
          { label: 'Anima check', value: animaCheckLine },
        ]}
        ledger="Stage 6 of 11"
      />
      <Marginalia id="note-gift">
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Techniques">
          are capped at {picks} picks at this stage; the budget comes from your distinctions.
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
          name="Resonance"
          value={resonanceName}
          done={completion.resonance}
          gated={!completion.techniques}
          gateReason="Choose your techniques first"
          open={completion.techniques && !completion.resonance}
        >
          <EntryList label="Resonances">
            {resonances.map((resonance) => {
              const isSelected = selectedResonanceId === resonance.id;
              return (
                <Entry
                  key={resonance.id}
                  name={resonance.name}
                  tag={resonance.resonance_affinity ?? 'Resonance'}
                  chosen={isSelected}
                  open={isSelected}
                >
                  {resonance.description && <p>{resonance.description}</p>}
                  <CodexLine entryId={resonance.codex_entry_id} name={resonance.name} />
                  <EntryDoors
                    chooseLabel={`Choose ${resonance.name}`}
                    onChoose={() => handleSelectResonance(resonance.id)}
                    chosen={isSelected}
                  />
                </Entry>
              );
            })}
          </EntryList>
        </FunnelStep>

        <FunnelStep
          n={5}
          name={copy?.anima_check_heading ?? 'Anima Check'}
          value={animaCheckLine}
          done={completion.anima}
          gated={!completion.resonance}
          gateReason="Choose a resonance first"
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

      <h2 className="section-h" id="glimpse-heading">
        {copy?.magic_glimpse_heading ?? 'The Glimpse'}
      </h2>
      <GlimpseSection
        draft={draft}
        glimpseProseField={register('glimpse_story')}
        heading={copy?.magic_glimpse_heading}
      />
    </ChapterLeaf>
  );
}
