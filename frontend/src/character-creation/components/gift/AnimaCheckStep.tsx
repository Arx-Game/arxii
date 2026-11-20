/**
 * AnimaCheckStep (#3630, #5220): the final step of the Gift funnel.
 *
 * The player names the stat + skill every one of their casts rolls (the
 * "Anima Check"), plus an optional name for their Anima Ritual. Per Tehom's
 * 2026-07-16 ruling, the copy is explicit that this choice is purely
 * mechanical: how a cast *looks and feels* in a scene is always the
 * player's to describe, never dictated by this pick. The step's own name
 * (in GiftStage's funnel) carries the heading, so this renders only the
 * intro sentence and the picks.
 *
 * Each pick is one dropdown (#5220, owner ruling 2026-11-20: "the whole weird
 * boxes of each stat and skill are terrible"). They were a button per
 * statistic and per skill, 28 boxes of uneven width on production's content.
 * A dropdown lists the suggested option first and the rest under their
 * categories.
 */

import { useMemo } from 'react';
import type { UseFormRegister } from 'react-hook-form';
import { Field } from '../../folio';
import {
  useCGExplanations,
  usePathSkillSuggestions,
  useSkills,
  useStatDefinitions,
  useUpdateDraft,
} from '../../queries';
import { MAGIC_SKILL_CATEGORY } from '../../constants';
import type { CharacterDraft } from '../../types';
import { capitalize } from '../../utils';
import type { GiftFormValues } from '../GiftStage';

interface AnimaCheckStepProps {
  draft: CharacterDraft;
  /** GiftStage's shared react-hook-form register — a single beforeLeave save
   * covers ritual name + motif + glimpse. */
  register: UseFormRegister<GiftFormValues>;
}

/** One category of a dropdown: its heading and the options under it, in the order given. */
interface OptionGroup {
  label: string;
  options: { id: number; name: string }[];
}

/** Options gathered under their category headings, categories in first-seen order. */
function groupByCategory<T extends { id: number }>(
  items: T[],
  categoryOf: (item: T) => string,
  nameOf: (item: T) => string
): OptionGroup[] {
  const groups = new Map<string, OptionGroup>();
  for (const item of items) {
    const label = categoryOf(item);
    const group = groups.get(label) ?? { label, options: [] };
    group.options.push({ id: item.id, name: nameOf(item) });
    groups.set(label, group);
  }
  return [...groups.values()];
}

interface PickSelectProps {
  id: string;
  label: string;
  value: number | null;
  suggested: { id: number; name: string } | null;
  groups: OptionGroup[];
  onChange: (value: number) => void;
}

/** A required pick as one dropdown: the suggested option first, the rest by category. */
function PickSelect({ id, label, value, suggested, groups, onChange }: PickSelectProps) {
  return (
    <Field id={id} label={label}>
      <select
        id={id}
        value={value ?? ''}
        onChange={(event) => {
          if (event.target.value !== '') onChange(Number(event.target.value));
        }}
      >
        {value == null && (
          <option value="" disabled>
            Select
          </option>
        )}
        {suggested && <option value={suggested.id}>{suggested.name} (suggested)</option>}
        {groups.map((group) => (
          <optgroup key={group.label} label={group.label}>
            {group.options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </Field>
  );
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

  // The suggested option stands first in its dropdown and is left out of its category,
  // so no statistic or skill is listed twice.
  const statGroups = useMemo(
    () =>
      groupByCategory(
        (statDefinitions ?? []).filter((stat) => stat.id !== suggestedStat?.id),
        (stat) => capitalize(stat.category),
        (stat) => capitalize(stat.name)
      ),
    [statDefinitions, suggestedStat]
  );

  // Magical rolls add magic-category skills as terms (#4450), so one is never the
  // Anima Check pick; the server validator refuses it too.
  const pickableSkills = useMemo(
    () => (skills ?? []).filter((skill) => skill.category !== MAGIC_SKILL_CATEGORY),
    [skills]
  );
  const suggestedSkill = useMemo(
    () => pickableSkills.find((skill) => skill.id === suggestedSkillId) ?? null,
    [pickableSkills, suggestedSkillId]
  );
  const skillGroups = useMemo(
    () =>
      groupByCategory(
        pickableSkills.filter((skill) => skill.id !== suggestedSkill?.id),
        (skill) => skill.category_display || capitalize(skill.category),
        (skill) => skill.name
      ),
    [pickableSkills, suggestedSkill]
  );

  const handleStatChange = (value: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { anima_check_stat_id: value } },
    });
  };

  const handleSkillChange = (value: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { anima_check_skill_id: value } },
    });
  };

  return (
    <>
      {copy?.anima_check_intro && <p className="section-desc">{copy.anima_check_intro}</p>}

      <PickSelect
        id="anima-check-stat"
        label="Statistic"
        value={statId}
        suggested={
          suggestedStat ? { id: suggestedStat.id, name: capitalize(suggestedStat.name) } : null
        }
        groups={statGroups}
        onChange={handleStatChange}
      />

      <PickSelect
        id="anima-check-skill"
        label="Skill"
        value={skillId}
        suggested={suggestedSkill ? { id: suggestedSkill.id, name: suggestedSkill.name } : null}
        groups={skillGroups}
        onChange={handleSkillChange}
      />

      <Field id="ritual-name" label="Ritual name">
        <input id="ritual-name" type="text" maxLength={100} {...register('anima_ritual_name')} />
      </Field>
    </>
  );
}
