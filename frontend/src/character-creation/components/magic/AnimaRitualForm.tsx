/**
 * AnimaRitualForm Component
 *
 * Allows players to design their anima recovery ritual by selecting:
 * - Stat (Strength, Agility, etc.)
 * - Skill (must match selected path skills)
 * - Optional Specialization
 * - Resonance
 * - Description of their personal ritual
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useResonances, useSkills, useStatDefinitions } from '../../queries';
import type { DraftData } from '../../types';

interface AnimaRitualFormProps {
  draftData: DraftData;
  onUpdate: (updates: Partial<DraftData>) => void;
}

export function AnimaRitualForm({ draftData, onUpdate }: AnimaRitualFormProps) {
  const { data: stats, isLoading: statsLoading } = useStatDefinitions();
  const { data: skills, isLoading: skillsLoading } = useSkills();
  const { data: resonances, isLoading: resonancesLoading } = useResonances();

  const selectedStatId = draftData.draft_ritual_stat_id;
  const selectedSkillId = draftData.draft_ritual_skill_id;
  const selectedSpecId = draftData.draft_ritual_specialization_id;
  const selectedResonanceId = draftData.draft_ritual_resonance_id;
  const description = draftData.draft_ritual_description ?? '';

  // Get the selected skill's specializations
  const selectedSkill = skills?.find((s) => s.id === selectedSkillId);
  const availableSpecs = selectedSkill?.specializations ?? [];

  const handleStatChange = (value: string) => {
    onUpdate({ draft_ritual_stat_id: parseInt(value) });
  };

  const handleSkillChange = (value: string) => {
    onUpdate({
      draft_ritual_skill_id: parseInt(value),
      draft_ritual_specialization_id: null, // Reset spec when skill changes
    });
  };

  const handleSpecChange = (value: string) => {
    onUpdate({
      draft_ritual_specialization_id: value === 'none' ? null : parseInt(value),
    });
  };

  const handleResonanceChange = (value: string) => {
    onUpdate({ draft_ritual_resonance_id: parseInt(value) });
  };

  const handleDescriptionChange = (value: string) => {
    onUpdate({ draft_ritual_description: value });
  };

  const isLoading = statsLoading || skillsLoading || resonancesLoading;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Anima Recovery Ritual</CardTitle>
        <CardDescription>
          Design your personal ritual for recovering anima. Choose a stat, skill, and resonance that
          defines how you draw magical energy back into yourself.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Stat Selection */}
        <div className="space-y-2">
          <Label>Stat</Label>
          <p className="text-xs text-muted-foreground">
            Which attribute do you draw upon during your ritual?
          </p>
          {isLoading ? (
            <div className="h-10 animate-pulse rounded bg-muted" />
          ) : (
            <Select value={selectedStatId?.toString() ?? ''} onValueChange={handleStatChange}>
              <SelectTrigger>
                <SelectValue placeholder="Select a stat..." />
              </SelectTrigger>
              <SelectContent>
                {stats?.map((stat) => (
                  <SelectItem key={stat.id} value={stat.id.toString()}>
                    {stat.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Skill Selection */}
        <div className="space-y-2">
          <Label>Skill</Label>
          <p className="text-xs text-muted-foreground">
            Which skill is central to performing your ritual?
          </p>
          {isLoading ? (
            <div className="h-10 animate-pulse rounded bg-muted" />
          ) : (
            <Select value={selectedSkillId?.toString() ?? ''} onValueChange={handleSkillChange}>
              <SelectTrigger>
                <SelectValue placeholder="Select a skill..." />
              </SelectTrigger>
              <SelectContent>
                {skills?.map((skill) => (
                  <SelectItem key={skill.id} value={skill.id.toString()}>
                    {skill.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Specialization Selection (Optional) */}
        {selectedSkillId && availableSpecs.length > 0 && (
          <div className="space-y-2">
            <Label>Specialization (Optional)</Label>
            <p className="text-xs text-muted-foreground">
              Does a specific specialization apply to your ritual?
            </p>
            <Select value={selectedSpecId?.toString() ?? 'none'} onValueChange={handleSpecChange}>
              <SelectTrigger>
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {availableSpecs.map((spec) => (
                  <SelectItem key={spec.id} value={spec.id.toString()}>
                    {spec.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {/* Resonance Selection */}
        <div className="space-y-2">
          <Label>Resonance</Label>
          <p className="text-xs text-muted-foreground">
            Which resonance channels into your recovery?
          </p>
          {isLoading ? (
            <div className="h-10 animate-pulse rounded bg-muted" />
          ) : (
            <Select
              value={selectedResonanceId?.toString() ?? ''}
              onValueChange={handleResonanceChange}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a resonance..." />
              </SelectTrigger>
              <SelectContent>
                {resonances?.map((resonance) => (
                  <SelectItem key={resonance.id} value={resonance.id.toString()}>
                    {resonance.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Description */}
        <div className="space-y-2">
          <Label htmlFor="ritual-description">Ritual Description</Label>
          <p className="text-xs text-muted-foreground">
            Describe how your character performs this ritual in their own unique way.
          </p>
          <Textarea
            id="ritual-description"
            value={description}
            onChange={(e) => handleDescriptionChange(e.target.value)}
            placeholder="e.g., Under moonlight, I trace sigils in the air while humming an ancient melody..."
            rows={4}
          />
        </div>
      </CardContent>
    </Card>
  );
}
