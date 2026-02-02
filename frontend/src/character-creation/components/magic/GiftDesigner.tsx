/**
 * GiftDesigner Component
 *
 * Allows players to design a custom gift by selecting:
 * - Name
 * - Affinity (Celestial/Primal/Abyssal)
 * - 1-2 Resonances
 * - Description
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { Moon, Sparkles, Sun, TreePine } from 'lucide-react';
import { useState } from 'react';
import { useAffinities, useCreateDraftGift, useResonances } from '../../queries';
import type { AffinityType, DraftGift, Resonance } from '../../types';

interface GiftDesignerProps {
  onGiftCreated: (gift: DraftGift) => void;
  onCancel?: () => void;
}

const MAX_RESONANCES = 2;
const MIN_RESONANCES = 1;

export function GiftDesigner({ onGiftCreated, onCancel }: GiftDesignerProps) {
  const [name, setName] = useState('');
  const [selectedAffinity, setSelectedAffinity] = useState<number | null>(null);
  const [selectedResonances, setSelectedResonances] = useState<number[]>([]);
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { data: affinities, isLoading: affinitiesLoading } = useAffinities();
  const { data: resonances, isLoading: resonancesLoading } = useResonances();
  const createDraftGift = useCreateDraftGift();

  const getAffinityStyle = (type: AffinityType | string) => {
    switch (type) {
      case 'celestial':
        return {
          icon: Sun,
          bgClass: 'bg-amber-500/10',
          borderClass: 'border-amber-500/50',
          textClass: 'text-amber-500',
        };
      case 'primal':
        return {
          icon: TreePine,
          bgClass: 'bg-emerald-500/10',
          borderClass: 'border-emerald-500/50',
          textClass: 'text-emerald-500',
        };
      case 'abyssal':
        return {
          icon: Moon,
          bgClass: 'bg-violet-500/10',
          borderClass: 'border-violet-500/50',
          textClass: 'text-violet-500',
        };
      default:
        return {
          icon: Sparkles,
          bgClass: 'bg-muted',
          borderClass: 'border-muted',
          textClass: 'text-muted-foreground',
        };
    }
  };

  const handleResonanceToggle = (resonance: Resonance) => {
    if (selectedResonances.includes(resonance.id)) {
      setSelectedResonances((prev) => prev.filter((id) => id !== resonance.id));
    } else if (selectedResonances.length < MAX_RESONANCES) {
      setSelectedResonances((prev) => [...prev, resonance.id]);
    }
  };

  const handleSubmit = async () => {
    setError(null);

    if (!name.trim()) {
      setError('Gift name is required');
      return;
    }
    if (!selectedAffinity) {
      setError('Please select an affinity');
      return;
    }
    if (selectedResonances.length < MIN_RESONANCES) {
      setError('Please select at least one resonance');
      return;
    }

    try {
      const gift = await createDraftGift.mutateAsync({
        name: name.trim(),
        affinity: selectedAffinity,
        resonances: selectedResonances,
        description: description.trim(),
      });
      onGiftCreated(gift);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create gift');
    }
  };

  const isLoading = affinitiesLoading || resonancesLoading;
  const canSubmit =
    name.trim() &&
    selectedAffinity &&
    selectedResonances.length >= MIN_RESONANCES &&
    !createDraftGift.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Design Your Gift</CardTitle>
        <CardDescription>
          Create a unique magical gift that defines your character's powers.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Gift Name */}
        <div className="space-y-2">
          <Label htmlFor="gift-name">Gift Name</Label>
          <Input
            id="gift-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Whispers of Shadow"
            maxLength={100}
          />
        </div>

        {/* Affinity Selection */}
        <div className="space-y-2">
          <Label>Affinity</Label>
          <p className="text-xs text-muted-foreground">
            Choose the magical source that powers your gift.
          </p>
          {isLoading ? (
            <div className="flex gap-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-20 w-full animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : (
            <div className="grid gap-2 sm:grid-cols-3">
              {affinities?.map((affinity) => {
                const affinityType = affinity.name.toLowerCase() as AffinityType;
                const style = getAffinityStyle(affinityType);
                const Icon = style.icon;
                const isSelected = selectedAffinity === affinity.id;

                return (
                  <button
                    key={affinity.id}
                    type="button"
                    onClick={() => setSelectedAffinity(affinity.id)}
                    className={cn(
                      'flex flex-col items-center gap-1 rounded-lg border p-3 transition-all',
                      style.bgClass,
                      isSelected ? 'ring-2 ring-primary' : 'hover:ring-1 hover:ring-primary/50',
                      style.borderClass
                    )}
                  >
                    <Icon className={cn('h-6 w-6', style.textClass)} />
                    <span className="text-sm font-medium capitalize">{affinity.name}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Resonance Selection */}
        <div className="space-y-2">
          <Label>
            Resonances ({selectedResonances.length}/{MAX_RESONANCES})
          </Label>
          <p className="text-xs text-muted-foreground">
            Select 1-2 resonances that define your gift's magical style.
          </p>
          {isLoading ? (
            <div className="flex flex-wrap gap-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-8 w-20 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              {resonances?.map((resonance) => {
                const isSelected = selectedResonances.includes(resonance.id);
                const isDisabled = !isSelected && selectedResonances.length >= MAX_RESONANCES;

                return (
                  <Button
                    key={resonance.id}
                    variant={isSelected ? 'default' : 'outline'}
                    size="sm"
                    disabled={isDisabled}
                    onClick={() => handleResonanceToggle(resonance)}
                    title={resonance.description}
                  >
                    {resonance.name}
                  </Button>
                );
              })}
            </div>
          )}
        </div>

        {/* Description */}
        <div className="space-y-2">
          <Label htmlFor="gift-description">Description</Label>
          <Textarea
            id="gift-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the nature and manifestation of your gift..."
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
            {createDraftGift.isPending ? 'Creating...' : 'Create Gift'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
