/**
 * AnimaCheckStep (#3630) — the final step of the Gift funnel, as choice rows.
 *
 * The player names the stat + skill every one of their casts rolls (the
 * "Anima Check"), plus an optional name for their Anima Ritual. Per Tehom's
 * 2026-07-16 ruling, the copy is explicit that this choice is purely
 * mechanical — how a cast *looks and feels* in a scene is always the
 * player's to describe, never dictated by this pick. The step's own name
 * (in GiftStage's funnel) now carries the heading, so this renders only the
 * intro sentence and the picks.
 */

import { useMemo } from 'react';
import type { UseFormRegister } from 'react-hook-form';
import { ChoiceRow, Field } from '../../folio';
import {
  useCGExplanations,
  usePathSkillSuggestions,
  useSkills,
  useStatDefinitions,
  useUpdateDraft,
} from '../../queries';
import type { CharacterDraft } from '../../types';
import type { GiftFormValues } from '../GiftStage';

interface AnimaCheckStepProps {
  draft: CharacterDraft;
  /** GiftStage's shared react-hook-form register — a single beforeLeave save
   * covers ritual name + motif + glimpse. */
  register: UseFormRegister<GiftFormValues>;
}

export function AnimaCheckStep({ draft, register }: AnimaCheckStepProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: statDefinitions } = useStatDefinitions();
  const { data: skills } = useSkills();
  const { data: pathSuggestions } = usePathSkillSuggestions(draft.selected_path?.id);

  const draftData = draft.draft_data;
  const statId = draftData.anima_check_stat_id ?? null;
  const skillId = draftData.anima_check_skill_id ?? null;

  // Suggested pairing: Willpower is the game's own default Anima Check stat
  // when a player leaves this unset (see
  // world.magic.services.anima.provision_player_anima_ritual's fallback), so
  // it's surfaced first here too. The suggested skill is the path's
  // highest-suggested skill (usePathSkillSuggestions — the same data
  // SkillsSection uses to pre-fill skill allocation). This is a light nudge
  // only: nothing here restricts the player's actual pick.
  const suggestedStat = useMemo(
    () => statDefinitions?.find((stat) => stat.name.toLowerCase() === 'willpower') ?? null,
    [statDefinitions]
  );
  const suggestedSkillId = useMemo(() => {
    if (!pathSuggestions || pathSuggestions.length === 0) return null;
    return [...pathSuggestions].sort((a, b) => b.suggested_value - a.suggested_value)[0].skill_id;
  }, [pathSuggestions]);

  const sortedStats = useMemo(() => {
    if (!statDefinitions) return [];
    if (!suggestedStat) return statDefinitions;
    return [suggestedStat, ...statDefinitions.filter((stat) => stat.id !== suggestedStat.id)];
  }, [statDefinitions, suggestedStat]);

  const sortedSkills = useMemo(() => {
    if (!skills) return [];
    if (suggestedSkillId == null) return skills;
    const suggested = skills.find((skill) => skill.id === suggestedSkillId);
    if (!suggested) return skills;
    return [suggested, ...skills.filter((skill) => skill.id !== suggestedSkillId)];
  }, [skills, suggestedSkillId]);

  const handleStatChange = (value: number | null) => {
    if (value == null) return;
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { anima_check_stat_id: value } },
    });
  };

  const handleSkillChange = (value: number | null) => {
    if (value == null) return;
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { anima_check_skill_id: value } },
    });
  };

  return (
    <>
      {copy?.anima_check_intro && <p className="section-desc">{copy.anima_check_intro}</p>}

      <ChoiceRow
        label="Statistic"
        options={sortedStats.map((stat) => ({
          value: stat.id,
          label: suggestedStat?.id === stat.id ? `${stat.name} (suggested)` : stat.name,
        }))}
        value={statId}
        onChange={handleStatChange}
      />

      <ChoiceRow
        label="Skill"
        options={sortedSkills.map((skill) => ({
          value: skill.id,
          label: suggestedSkillId === skill.id ? `${skill.name} (suggested)` : skill.name,
        }))}
        value={skillId}
        onChange={handleSkillChange}
      />

      <Field
        id="ritual-name"
        label="Ritual name"
        hint="Optional. Defaults to “[Character]’s Anima Ritual” if left blank."
      >
        <input id="ritual-name" type="text" maxLength={100} {...register('anima_ritual_name')} />
      </Field>
    </>
  );
}
