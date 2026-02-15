/**
 * GiftDesigner Component
 *
 * Allows players to design a custom gift by selecting:
 * - Name
 * - 1-2 Resonances (affinity is derived from chosen resonances)
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
import { useCreateDraftGift, useResonances } from '../../queries';
import type { DraftGift, ProjectedResonance, Resonance } from '../../types';

interface GiftDesignerProps {
  onGiftCreated: (gift: DraftGift) => void;
  onCancel?: () => void;
  projectedResonances?: ProjectedResonance[];
}

const MAX_RESONANCES = 2;
const MIN_RESONANCES = 1;

export function GiftDesigner({ onGiftCreated, onCancel, projectedResonances }: GiftDesignerProps) {
  const [name, setName] = useState('');
  const [selectedResonances, setSelectedResonances] = useState<number[]>([]);
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { data: resonances, isLoading: resonancesLoading } = useResonances();
  const createDraftGift = useCreateDraftGift();

  const getAffinityStyle = (type: string) => {
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
    if (selectedResonances.length < MIN_RESONANCES) {
      setError('Please select at least one resonance');
      return;
    }

    try {
      const gift = await createDraftGift.mutateAsync({
        name: name.trim(),
        resonances: selectedResonances,
        description: description.trim(),
      });
      onGiftCreated(gift);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create gift');
    }
  };

  const isLoading = resonancesLoading;
  const canSubmit =
    name.trim() && selectedResonances.length >= MIN_RESONANCES && !createDraftGift.isPending;

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
                const projected = projectedResonances?.find((p) => p.resonance_id === resonance.id);
                const hasExisting = projected && projected.total > 0;

                return (
                  <Button
                    key={resonance.id}
                    variant={isSelected ? 'default' : 'outline'}
                    size="sm"
                    disabled={isDisabled}
                    onClick={() => handleResonanceToggle(resonance)}
                    title={resonance.description}
                    className={cn(
                      !isSelected && hasExisting && 'border-green-500/50 bg-green-500/10'
                    )}
                  >
                    {resonance.name}
                    {hasExisting && !isSelected && (
                      <span className="ml-1 text-xs text-green-600">+{projected.total}</span>
                    )}
                  </Button>
                );
              })}
            </div>
          )}
        </div>

        {/* Derived Affinity (read-only) */}
        {selectedResonances.length > 0 && resonances && (
          <div className="space-y-2">
            <Label>Derived Affinity</Label>
            <p className="text-xs text-muted-foreground">
              Your gift's affinity is determined by your chosen resonances.
            </p>
            <div className="flex gap-2">
              {(() => {
                const counts: Record<string, number> = {};
                for (const resId of selectedResonances) {
                  const res = resonances.find((r) => r.id === resId);
                  if (res?.resonance_affinity) {
                    const affinityName = res.resonance_affinity;
                    counts[affinityName] = (counts[affinityName] || 0) + 1;
                  }
                }
                return Object.entries(counts).map(([affinityName, count]) => {
                  const style = getAffinityStyle(affinityName);
                  const Icon = style.icon;
                  return (
                    <div
                      key={affinityName}
                      className={cn(
                        'flex items-center gap-1.5 rounded-lg border px-3 py-1.5',
                        style.bgClass,
                        style.borderClass
                      )}
                    >
                      <Icon className={cn('h-4 w-4', style.textClass)} />
                      <span className="text-sm font-medium capitalize">{affinityName}</span>
                      {Object.keys(counts).length > 1 && (
                        <span className="text-xs text-muted-foreground">({count})</span>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          </div>
        )}

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
