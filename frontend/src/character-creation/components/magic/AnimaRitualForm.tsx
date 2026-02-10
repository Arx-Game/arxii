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
import { Combobox, type ComboboxItem } from '@/components/ui/combobox';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useEffect, useMemo, useState } from 'react';
import {
  useCreateDraftAnimaRitual,
  useDraftAnimaRitual,
  useResonances,
  useSkills,
  useStatDefinitions,
  useUpdateDraftAnimaRitual,
} from '../../queries';
import type { ProjectedResonance, Stats } from '../../types';

interface AnimaRitualFormProps {
  draftStats?: Stats;
  draftSkills?: Record<string, number>;
  projectedResonances?: ProjectedResonance[];
}

export function AnimaRitualForm({
  draftStats,
  draftSkills,
  projectedResonances,
}: AnimaRitualFormProps) {
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

  // Build combobox items with green intensity shading based on draft investments
  const statItems: ComboboxItem[] = useMemo(() => {
    if (!stats) return [];
    return stats.map((stat) => {
      const rawValue = draftStats?.[stat.name.toLowerCase() as keyof Stats];
      const displayValue = rawValue != null ? Math.floor(rawValue / 10) : 0;
      const intensity = Math.max(0, displayValue - 2);
      return {
        value: stat.id.toString(),
        label: stat.name,
        secondaryText: displayValue > 2 ? displayValue.toString() : undefined,
        intensity,
      };
    });
  }, [stats, draftStats]);

  const skillItems: ComboboxItem[] = useMemo(() => {
    if (!skills) return [];
    return skills.map((skill) => {
      const invested = draftSkills?.[skill.id.toString()] ?? 0;
      const intensity = Math.min(3, Math.floor(invested / 10));
      return {
        value: skill.id.toString(),
        label: skill.name,
        secondaryText: invested > 0 ? invested.toString() : undefined,
        intensity,
        group: skill.category_display,
      };
    });
  }, [skills, draftSkills]);

  const resonanceItems: ComboboxItem[] = useMemo(() => {
    if (!resonances) return [];
    return resonances.map((res) => {
      const projected = projectedResonances?.find((p) => p.resonance_id === res.id);
      const total = projected?.total ?? 0;
      const intensity = total > 0 ? Math.min(5, Math.ceil(total / 10)) : 0;
      return {
        value: res.id.toString(),
        label: res.name,
        secondaryText: total > 0 ? `+${total}` : undefined,
        intensity,
      };
    });
  }, [resonances, projectedResonances]);

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
            <Combobox
              items={statItems}
              value={selectedStatId?.toString() ?? ''}
              onValueChange={handleStatChange}
              placeholder="Select a stat..."
              searchPlaceholder="Search stats..."
            />
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
            <Combobox
              items={skillItems}
              value={selectedSkillId?.toString() ?? ''}
              onValueChange={handleSkillChange}
              placeholder="Select a skill..."
              searchPlaceholder="Search skills..."
            />
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
            <Combobox
              items={resonanceItems}
              value={selectedResonanceId?.toString() ?? ''}
              onValueChange={handleResonanceChange}
              placeholder="Select a resonance..."
              searchPlaceholder="Search resonances..."
            />
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
