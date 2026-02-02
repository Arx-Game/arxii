/**
 * TechniqueBuilder Component
 *
 * Allows players to build techniques within their gift by selecting:
 * - Name
 * - Style (Manifestation, Subtle, etc.)
 * - Effect Type (Attack, Defense, etc.)
 * - Restrictions (optional, for power bonuses)
 * - Level (1-15)
 * - Description
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Textarea } from '@/components/ui/textarea';
import { Plus } from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  useCreateDraftTechnique,
  useEffectTypes,
  useRestrictions,
  useTechniqueStyles,
} from '../../queries';
import type { DraftTechnique, Restriction } from '../../types';

interface TechniqueBuilderProps {
  giftId: number;
  existingTechniques: DraftTechnique[];
  onTechniqueCreated: (technique: DraftTechnique) => void;
  onCancel?: () => void;
}

const MAX_LEVEL = 15;
const MIN_LEVEL = 1;

export function TechniqueBuilder({
  giftId,
  existingTechniques,
  onTechniqueCreated,
  onCancel,
}: TechniqueBuilderProps) {
  const [name, setName] = useState('');
  const [selectedStyle, setSelectedStyle] = useState<number | null>(null);
  const [selectedEffectType, setSelectedEffectType] = useState<number | null>(null);
  const [selectedRestrictions, setSelectedRestrictions] = useState<number[]>([]);
  const [level, setLevel] = useState(1);
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { data: styles, isLoading: stylesLoading } = useTechniqueStyles();
  const { data: effectTypes, isLoading: effectTypesLoading } = useEffectTypes();
  const { data: allRestrictions, isLoading: restrictionsLoading } = useRestrictions();
  const createDraftTechnique = useCreateDraftTechnique();

  // Filter restrictions to those allowed for the selected effect type
  const availableRestrictions = useMemo(() => {
    if (!allRestrictions || !selectedEffectType) return [];
    return allRestrictions.filter(
      (r) =>
        r.allowed_effect_type_ids.length === 0 ||
        r.allowed_effect_type_ids.includes(selectedEffectType)
    );
  }, [allRestrictions, selectedEffectType]);

  // Calculate power bonus from restrictions
  const totalPowerBonus = useMemo(() => {
    if (!allRestrictions) return 0;
    return selectedRestrictions.reduce((sum, id) => {
      const restriction = allRestrictions.find((r) => r.id === id);
      return sum + (restriction?.power_bonus ?? 0);
    }, 0);
  }, [allRestrictions, selectedRestrictions]);

  // Get selected effect type details
  const selectedEffectDetails = useMemo(() => {
    if (!effectTypes || !selectedEffectType) return null;
    return effectTypes.find((e) => e.id === selectedEffectType);
  }, [effectTypes, selectedEffectType]);

  // Calculate tier from level
  const tier = Math.ceil(level / 5);

  // Calculate estimated power
  const estimatedPower = useMemo(() => {
    if (!selectedEffectDetails?.has_power_scaling) return null;
    const basePower = selectedEffectDetails.base_power ?? 0;
    return basePower + level + totalPowerBonus;
  }, [selectedEffectDetails, level, totalPowerBonus]);

  const handleRestrictionToggle = (restriction: Restriction) => {
    if (selectedRestrictions.includes(restriction.id)) {
      setSelectedRestrictions((prev) => prev.filter((id) => id !== restriction.id));
    } else {
      setSelectedRestrictions((prev) => [...prev, restriction.id]);
    }
  };

  const handleSubmit = async () => {
    setError(null);

    if (!name.trim()) {
      setError('Technique name is required');
      return;
    }
    if (!selectedStyle) {
      setError('Please select a style');
      return;
    }
    if (!selectedEffectType) {
      setError('Please select an effect type');
      return;
    }

    try {
      const technique = await createDraftTechnique.mutateAsync({
        name: name.trim(),
        gift: giftId,
        style: selectedStyle,
        effect_type: selectedEffectType,
        restrictions: selectedRestrictions,
        level,
        description: description.trim(),
      });
      onTechniqueCreated(technique);
      // Reset form
      setName('');
      setSelectedStyle(null);
      setSelectedEffectType(null);
      setSelectedRestrictions([]);
      setLevel(1);
      setDescription('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create technique');
    }
  };

  const isLoading = stylesLoading || effectTypesLoading || restrictionsLoading;
  const canSubmit =
    name.trim() && selectedStyle && selectedEffectType && !createDraftTechnique.isPending;

  // Mark existingTechniques as used (for future validation)
  void existingTechniques;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Plus className="h-5 w-5" />
          Build New Technique
        </CardTitle>
        <CardDescription>
          Create a magical technique within your gift. Each technique has a style, effect, and
          optional restrictions for bonus power.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Technique Name */}
        <div className="space-y-2">
          <Label htmlFor="technique-name">Technique Name</Label>
          <Input
            id="technique-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Shadow Strike"
            maxLength={100}
          />
        </div>

        {/* Style Selection */}
        <div className="space-y-2">
          <Label>Style</Label>
          <p className="text-xs text-muted-foreground">How does this technique manifest?</p>
          {isLoading ? (
            <div className="h-10 animate-pulse rounded bg-muted" />
          ) : (
            <Select
              value={selectedStyle?.toString() ?? ''}
              onValueChange={(v) => setSelectedStyle(parseInt(v))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a style..." />
              </SelectTrigger>
              <SelectContent>
                {styles?.map((style) => (
                  <SelectItem key={style.id} value={style.id.toString()}>
                    {style.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Effect Type Selection */}
        <div className="space-y-2">
          <Label>Effect Type</Label>
          <p className="text-xs text-muted-foreground">What does this technique do?</p>
          {isLoading ? (
            <div className="h-10 animate-pulse rounded bg-muted" />
          ) : (
            <Select
              value={selectedEffectType?.toString() ?? ''}
              onValueChange={(v) => {
                setSelectedEffectType(parseInt(v));
                // Clear restrictions when effect type changes
                setSelectedRestrictions([]);
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select an effect type..." />
              </SelectTrigger>
              <SelectContent>
                {effectTypes?.map((effect) => (
                  <SelectItem key={effect.id} value={effect.id.toString()}>
                    {effect.name}
                    {effect.has_power_scaling && ` (Base: ${effect.base_power})`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {selectedEffectDetails && (
            <p className="text-xs text-muted-foreground">{selectedEffectDetails.description}</p>
          )}
        </div>

        {/* Level Selection */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Level</Label>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{level}</span>
              <Badge variant="outline">Tier {tier}</Badge>
            </div>
          </div>
          <Slider
            value={[level]}
            min={MIN_LEVEL}
            max={MAX_LEVEL}
            step={1}
            onValueChange={([v]) => setLevel(v)}
          />
          <p className="text-xs text-muted-foreground">
            Higher levels increase power but require more investment.
          </p>
        </div>

        {/* Restrictions (Optional) */}
        {selectedEffectType && (
          <div className="space-y-2">
            <Label>Restrictions (Optional)</Label>
            <p className="text-xs text-muted-foreground">
              Add limitations to gain power bonuses. Current bonus: +{totalPowerBonus}
            </p>
            {restrictionsLoading ? (
              <div className="flex flex-wrap gap-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-8 w-24 animate-pulse rounded bg-muted" />
                ))}
              </div>
            ) : availableRestrictions.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {availableRestrictions.map((restriction) => {
                  const isSelected = selectedRestrictions.includes(restriction.id);
                  return (
                    <Button
                      key={restriction.id}
                      variant={isSelected ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => handleRestrictionToggle(restriction)}
                      title={restriction.description}
                    >
                      {restriction.name} (+{restriction.power_bonus})
                    </Button>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                No restrictions available for this effect type.
              </p>
            )}
          </div>
        )}

        {/* Power Preview */}
        {selectedEffectDetails && (
          <div className="rounded-lg border bg-muted/50 p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Power Preview</span>
              {estimatedPower !== null ? (
                <Badge>{estimatedPower} Power</Badge>
              ) : (
                <Badge variant="secondary">Binary Effect</Badge>
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {estimatedPower !== null
                ? `Base (${selectedEffectDetails.base_power}) + Level (${level}) + Restrictions (+${totalPowerBonus})`
                : 'This effect type does not scale with power.'}
            </p>
          </div>
        )}

        {/* Description */}
        <div className="space-y-2">
          <Label htmlFor="technique-description">Description</Label>
          <Textarea
            id="technique-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe how this technique works..."
            rows={3}
          />
        </div>

        {/* Error Display */}
        {error && <p className="text-sm text-destructive">{error}</p>}

        {/* Actions */}
        <div className="flex justify-end gap-2">
          {onCancel && (
            <Button variant="outline" onClick={onCancel}>
              Cancel
            </Button>
          )}
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {createDraftTechnique.isPending ? 'Creating...' : 'Add Technique'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
