/**
 * Family Selection Component
 *
 * Allows players to:
 * 1. Join existing family with open positions
 * 2. Create new commoner family (simplified MVP)
 * 3. Select orphan/unknown family
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { HelpCircle, Plus } from 'lucide-react';
import { useState } from 'react';
import { useFamilies, useFamiliesWithOpenPositions, useUpdateDraft } from '../queries';
import type { CharacterDraft, Family } from '../types';

interface FamilySelectionProps {
  draft: CharacterDraft;
  areaId: number;
}

type SelectionMode = 'join' | 'create' | 'orphan';

export function FamilySelection({ draft, areaId }: FamilySelectionProps) {
  const updateDraft = useUpdateDraft();
  const { data: allFamilies, isLoading: allFamiliesLoading } = useFamilies(areaId);
  const { data: familiesWithOpenPositions, isLoading: openPositionsLoading } =
    useFamiliesWithOpenPositions(areaId);

  // Determine current mode from draft state
  const getCurrentMode = (): SelectionMode => {
    if (draft.draft_data.lineage_is_orphan) return 'orphan';
    if (draft.family) return 'join';
    return 'join'; // default
  };

  const [mode, setMode] = useState<SelectionMode>(getCurrentMode());
  const [newFamilyName, setNewFamilyName] = useState('');
  const [newFamilyDescription, setNewFamilyDescription] = useState('');
  const [showAllFamilies, setShowAllFamilies] = useState(false);

  const handleModeChange = (newMode: SelectionMode) => {
    setMode(newMode);
    if (newMode === 'orphan') {
      updateDraft.mutate({
        draftId: draft.id,
        data: {
          family_id: null,
          draft_data: { ...draft.draft_data, lineage_is_orphan: true },
        },
      });
    } else {
      updateDraft.mutate({
        draftId: draft.id,
        data: { draft_data: { ...draft.draft_data, lineage_is_orphan: false } },
      });
    }
  };

  const handleFamilySelect = (familyId: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        family_id: parseInt(familyId, 10),
        draft_data: { ...draft.draft_data, lineage_is_orphan: false },
      },
    });
  };

  const handleCreateFamily = () => {
    // For MVP: Just set a placeholder in draft_data
    // Full implementation would call useCreateFamily mutation
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draft.draft_data,
          pending_family: {
            name: newFamilyName,
            description: newFamilyDescription,
            family_type: 'commoner',
          },
        },
      },
    });
  };

  // Combine families for display
  const familiesToShow = showAllFamilies ? allFamilies : familiesWithOpenPositions;

  const noblesFamilies = familiesToShow?.filter((f) => f.family_type === 'noble') ?? [];
  const commonerFamilies = familiesToShow?.filter((f) => f.family_type === 'commoner') ?? [];

  return (
    <div className="space-y-6">
      {/* Mode Selection */}
      <RadioGroup value={mode} onValueChange={(val) => handleModeChange(val as SelectionMode)}>
        <div className="space-y-3">
          {/* Join Existing Family */}
          <div
            className={cn(
              'flex items-center space-x-3 rounded-lg border p-4 transition-colors',
              mode === 'join' && 'border-primary bg-primary/5'
            )}
          >
            <RadioGroupItem value="join" id="mode-join" />
            <Label htmlFor="mode-join" className="flex-1 cursor-pointer font-medium">
              Join Existing Family
            </Label>
          </div>

          {/* Create New Family */}
          <div
            className={cn(
              'flex items-center space-x-3 rounded-lg border p-4 transition-colors',
              mode === 'create' && 'border-primary bg-primary/5'
            )}
          >
            <RadioGroupItem value="create" id="mode-create" />
            <Label htmlFor="mode-create" className="flex-1 cursor-pointer font-medium">
              Create New Family (Commoner)
            </Label>
          </div>

          {/* Orphan/Unknown */}
          <div
            className={cn(
              'flex items-center space-x-3 rounded-lg border p-4 transition-colors',
              mode === 'orphan' && 'border-primary bg-primary/5'
            )}
          >
            <RadioGroupItem value="orphan" id="mode-orphan" />
            <Label htmlFor="mode-orphan" className="flex-1 cursor-pointer font-medium">
              Orphan / Unknown Family
            </Label>
          </div>
        </div>
      </RadioGroup>

      {/* Join Existing Family Content */}
      {mode === 'join' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium">Select Family</Label>
            <div className="flex items-center gap-2">
              <Switch
                checked={showAllFamilies}
                onCheckedChange={setShowAllFamilies}
                id="show-all"
              />
              <Label htmlFor="show-all" className="cursor-pointer text-sm text-muted-foreground">
                Show all families
              </Label>
            </div>
          </div>

          {(allFamiliesLoading || openPositionsLoading) && (
            <div className="h-20 animate-pulse rounded bg-muted" />
          )}

          {!allFamiliesLoading && !openPositionsLoading && (
            <div className="space-y-6">
              {/* Noble Houses */}
              {noblesFamilies.length > 0 && (
                <div className="space-y-3">
                  <Label className="text-sm font-medium text-muted-foreground">Noble Houses</Label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {noblesFamilies.map((family) => (
                      <FamilyCard
                        key={family.id}
                        family={family}
                        isSelected={draft.family?.id === family.id}
                        onSelect={() => handleFamilySelect(family.id.toString())}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Commoner Families */}
              {commonerFamilies.length > 0 && (
                <div className="space-y-3">
                  <Label className="text-sm font-medium text-muted-foreground">
                    Commoner Families
                  </Label>
                  <Select
                    value={draft.family?.id?.toString() ?? ''}
                    onValueChange={handleFamilySelect}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select a family" />
                    </SelectTrigger>
                    <SelectContent>
                      {commonerFamilies.map((family) => (
                        <SelectItem key={family.id} value={family.id.toString()}>
                          {family.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {familiesToShow?.length === 0 && (
                <Card>
                  <CardContent className="py-6">
                    <p className="text-center text-sm text-muted-foreground">
                      {showAllFamilies
                        ? 'No families available for this area.'
                        : 'No families with open positions. Toggle "Show all families" to see more options.'}
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </div>
      )}

      {/* Create New Family Content */}
      {mode === 'create' && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Plus className="h-4 w-4" />
              Create New Commoner Family
            </CardTitle>
            <CardDescription>
              Create a new family for your character. You can add family members later.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="family-name">Family Name</Label>
              <Input
                id="family-name"
                value={newFamilyName}
                onChange={(e) => setNewFamilyName(e.target.value)}
                placeholder="Enter family name"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="family-description">Description (Optional)</Label>
              <Textarea
                id="family-description"
                value={newFamilyDescription}
                onChange={(e) => setNewFamilyDescription(e.target.value)}
                placeholder="Brief family history or background"
                rows={3}
              />
            </div>
            <Button
              onClick={handleCreateFamily}
              disabled={!newFamilyName.trim()}
              className="w-full"
            >
              Create Family
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Orphan Content */}
      {mode === 'orphan' && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <HelpCircle className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">No Family</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <CardDescription>
              Your character has no known family, or has been disowned. This may affect certain
              social interactions and background options.
            </CardDescription>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

interface FamilyCardProps {
  family: Family;
  isSelected: boolean;
  onSelect: () => void;
}

function FamilyCard({ family, isSelected, onSelect }: FamilyCardProps) {
  return (
    <Card
      className={cn(
        'cursor-pointer transition-all',
        isSelected && 'ring-2 ring-primary',
        !isSelected && 'hover:ring-1 hover:ring-primary/50'
      )}
      onClick={onSelect}
    >
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-sm">{family.name}</CardTitle>
      </CardHeader>
      {family.description && (
        <CardContent className="px-4 pb-4 pt-0">
          <CardDescription className="text-xs">{family.description}</CardDescription>
        </CardContent>
      )}
    </Card>
  );
}
