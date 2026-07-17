/**
 * AnimaCheckStep — final pick of the GiftStage funnel (#2426 Task 10).
 *
 * The player names the stat + skill every one of their casts rolls (the
 * "Anima Check"), plus an optional name for their Anima Ritual. Per Tehom's
 * 2026-07-16 ruling, the copy is explicit that this choice is purely
 * mechanical — how a cast *looks and feels* in a scene is always the
 * player's to describe, never dictated by this pick.
 */

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useMemo } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import {
  usePathSkillSuggestions,
  useSkills,
  useStatDefinitions,
  useUpdateDraft,
} from '../../queries';
import type { CharacterDraft } from '../../types';

interface AnimaCheckStepProps {
  draft: CharacterDraft;
  /** Registration for the ritual-name text field — owned by GiftStage's shared
   * form so a single beforeLeave save covers ritual name + motif + glimpse. */
  ritualNameField: UseFormRegisterReturn<'anima_ritual_name'>;
}

export function AnimaCheckStep({ draft, ritualNameField }: AnimaCheckStepProps) {
  const updateDraft = useUpdateDraft();
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

  const handleStatChange = (value: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          anima_check_stat_id: Number(value),
        },
      },
    });
  };

  const handleSkillChange = (value: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          anima_check_skill_id: Number(value),
        },
      },
    });
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        How does your magic move through you? The stat and skill you choose here are what every cast
        rolls — and how your casting looks and feels in a scene is always yours to describe.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="anima-stat">Stat</Label>
          <Select value={statId != null ? String(statId) : ''} onValueChange={handleStatChange}>
            <SelectTrigger id="anima-stat">
              <SelectValue placeholder="Choose a stat" />
            </SelectTrigger>
            <SelectContent>
              {sortedStats.map((stat) => (
                <SelectItem key={stat.id} value={String(stat.id)} className="capitalize">
                  {stat.name}
                  {suggestedStat?.id === stat.id ? ' (suggested)' : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="anima-skill">Skill</Label>
          <Select value={skillId != null ? String(skillId) : ''} onValueChange={handleSkillChange}>
            <SelectTrigger id="anima-skill">
              <SelectValue placeholder="Choose a skill" />
            </SelectTrigger>
            <SelectContent className="max-h-72 overflow-y-auto">
              {sortedSkills.map((skill) => (
                <SelectItem key={skill.id} value={String(skill.id)}>
                  {skill.name}
                  {suggestedSkillId === skill.id ? ' (suggested)' : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="max-w-md space-y-2">
        <Label htmlFor="anima-ritual-name">Ritual Name (optional)</Label>
        <Input
          id="anima-ritual-name"
          {...ritualNameField}
          placeholder="e.g. Sunrise Devotions"
          maxLength={100}
        />
        <p className="text-xs text-muted-foreground">
          Names your Anima Ritual. Defaults to &quot;[Character]&apos;s Anima Ritual&quot; if left
          blank.
        </p>
      </div>
    </div>
  );
}
