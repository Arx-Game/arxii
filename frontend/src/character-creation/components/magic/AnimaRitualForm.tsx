/**
 * AnimaRitualForm Component
 *
 * Allows players to design their anima recovery ritual by selecting:
 * - Stat (Strength, Agility, etc.)
 * - Skill (must match selected path skills)
 * - Optional Specialization
 * - Resonance
 * - Description of their personal ritual
 *
 * Uses DraftAnimaRitual model for persistent storage.
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
import { useEffect, useState } from 'react';
import {
  useCreateDraftAnimaRitual,
  useDraftAnimaRitual,
  useResonances,
  useSkills,
  useStatDefinitions,
  useUpdateDraftAnimaRitual,
} from '../../queries';

export function AnimaRitualForm() {
  const { data: stats, isLoading: statsLoading } = useStatDefinitions();
  const { data: skills, isLoading: skillsLoading } = useSkills();
  const { data: resonances, isLoading: resonancesLoading } = useResonances();
  const { data: draftRitual, isLoading: ritualLoading } = useDraftAnimaRitual();

  const createDraftRitual = useCreateDraftAnimaRitual();
  const updateDraftRitual = useUpdateDraftAnimaRitual();

  // Local state for form values (initialized from draftRitual when loaded)
  const [selectedStatId, setSelectedStatId] = useState<number | null>(null);
  const [selectedSkillId, setSelectedSkillId] = useState<number | null>(null);
  const [selectedSpecId, setSelectedSpecId] = useState<number | null>(null);
  const [selectedResonanceId, setSelectedResonanceId] = useState<number | null>(null);
  const [description, setDescription] = useState('');

  // Initialize form from existing draft ritual
  useEffect(() => {
    if (draftRitual) {
      setSelectedStatId(draftRitual.stat);
      setSelectedSkillId(draftRitual.skill);
      setSelectedSpecId(draftRitual.specialization);
      setSelectedResonanceId(draftRitual.resonance);
      setDescription(draftRitual.description);
    }
  }, [draftRitual]);

  // Get the selected skill's specializations
  const selectedSkill = skills?.find((s) => s.id === selectedSkillId);
  const availableSpecs = selectedSkill?.specializations ?? [];

  const saveRitual = (updates: {
    stat?: number;
    skill?: number;
    specialization?: number | null;
    resonance?: number;
    description?: string;
  }) => {
    const stat = updates.stat ?? selectedStatId;
    const skill = updates.skill ?? selectedSkillId;
    const resonance = updates.resonance ?? selectedResonanceId;
    const desc = updates.description ?? description;

    // Don't save if required fields are missing
    if (!stat || !skill || !resonance) return;

    if (draftRitual) {
      // Update existing ritual
      updateDraftRitual.mutate({
        ritualId: draftRitual.id,
        data: {
          stat,
          skill,
          specialization:
            updates.specialization !== undefined ? updates.specialization : selectedSpecId,
          resonance,
          description: desc,
        },
      });
    } else {
      // Create new ritual
      createDraftRitual.mutate({
        stat,
        skill,
        specialization:
          updates.specialization !== undefined ? updates.specialization : selectedSpecId,
        resonance,
        description: desc,
      });
    }
  };

  const handleStatChange = (value: string) => {
    const newStatId = parseInt(value);
    setSelectedStatId(newStatId);
    saveRitual({ stat: newStatId });
  };

  const handleSkillChange = (value: string) => {
    const newSkillId = parseInt(value);
    setSelectedSkillId(newSkillId);
    setSelectedSpecId(null); // Reset spec when skill changes
    saveRitual({ skill: newSkillId, specialization: null });
  };

  const handleSpecChange = (value: string) => {
    const newSpecId = value === 'none' ? null : parseInt(value);
    setSelectedSpecId(newSpecId);
    saveRitual({ specialization: newSpecId });
  };

  const handleResonanceChange = (value: string) => {
    const newResonanceId = parseInt(value);
    setSelectedResonanceId(newResonanceId);
    saveRitual({ resonance: newResonanceId });
  };

  const handleDescriptionChange = (value: string) => {
    setDescription(value);
    // Debounce description saves to avoid too many API calls
    // For now, save on blur instead of on every keystroke
  };

  const handleDescriptionBlur = () => {
    saveRitual({ description });
  };

  const isLoading = statsLoading || skillsLoading || resonancesLoading || ritualLoading;

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
            onBlur={handleDescriptionBlur}
            placeholder="e.g., Under moonlight, I trace sigils in the air while humming an ancient melody..."
            rows={4}
          />
        </div>
      </CardContent>
    </Card>
  );
}
