/**
 * Stage 3: Lineage (Family) Selection
 *
 * Family selection filtered by area, orphan option, or "Unknown" for special heritage.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { HelpCircle, Users } from 'lucide-react';
import { useFamilies, useUpdateDraft } from '../queries';
import type { CharacterDraft, Family } from '../types';
import { Stage } from '../types';

interface LineageStageProps {
  draft: CharacterDraft;
  onStageSelect: (stage: Stage) => void;
}

export function LineageStage({ draft, onStageSelect }: LineageStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: families, isLoading: familiesLoading } = useFamilies(draft.selected_area?.id);

  // If no area selected, prompt user
  if (!draft.selected_area) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="py-12 text-center"
      >
        <p className="mb-4 text-muted-foreground">Please select a starting area first.</p>
        <Button onClick={() => onStageSelect(Stage.ORIGIN)}>Go to Origin Selection</Button>
      </motion.div>
    );
  }

  // If beginnings has family_known = false, family is Unknown (e.g., Sleeper, Misbegotten)
  if (draft.selected_beginnings && !draft.selected_beginnings.family_known) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.3 }}
        className="space-y-8"
      >
        <div>
          <h2 className="text-2xl font-bold">Lineage</h2>
          <p className="mt-2 text-muted-foreground">Your character's family background.</p>
        </div>

        <Card className="max-w-md">
          <CardHeader>
            <div className="flex items-center gap-2">
              <HelpCircle className="h-5 w-5 text-amber-500" />
              <CardTitle className="text-base">Unknown Origins</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <CardDescription>
              As a {draft.selected_beginnings.name}, your true family origins are shrouded in
              mystery. This may be discovered through gameplay.
            </CardDescription>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  // Prompt to select beginnings if not selected
  if (!draft.selected_beginnings) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="py-12 text-center"
      >
        <p className="mb-4 text-muted-foreground">Please select a beginnings option first.</p>
        <Button onClick={() => onStageSelect(Stage.HERITAGE)}>Go to Heritage Selection</Button>
      </motion.div>
    );
  }

  // Normal upbringing - family selection
  const handleFamilySelect = (familyId: string) => {
    if (familyId === 'orphan') {
      updateDraft.mutate({ draftId: draft.id, data: { family_id: null, is_orphan: true } });
    } else {
      updateDraft.mutate({
        draftId: draft.id,
        data: { family_id: parseInt(familyId, 10), is_orphan: false },
      });
    }
  };

  const noblesFamilies = families?.filter((f) => f.family_type === 'noble') ?? [];
  const commonerFamilies = families?.filter((f) => f.family_type === 'commoner') ?? [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="text-2xl font-bold">Lineage</h2>
        <p className="mt-2 text-muted-foreground">
          Choose your character's family. Your family name will be appended to your character's
          first name.
        </p>
      </div>

      {/* Orphan option */}
      <Card
        className={cn(
          'max-w-md cursor-pointer transition-all',
          draft.is_orphan && 'ring-2 ring-primary',
          !draft.is_orphan && 'hover:ring-1 hover:ring-primary/50'
        )}
        onClick={() => handleFamilySelect('orphan')}
      >
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-base">Orphan / No Family</CardTitle>
            </div>
            <Switch checked={draft.is_orphan} />
          </div>
        </CardHeader>
        <CardContent>
          <CardDescription>
            Your character has no known family, or has been disowned.
          </CardDescription>
        </CardContent>
      </Card>

      {/* Family selection (disabled if orphan selected) */}
      {!draft.is_orphan && (
        <section className="space-y-4">
          <h3 className="text-lg font-semibold">Select Family</h3>

          {familiesLoading ? (
            <div className="h-10 animate-pulse rounded bg-muted" />
          ) : (
            <div className="space-y-6">
              {/* Noble Houses */}
              {noblesFamilies.length > 0 && (
                <div className="space-y-2">
                  <Label className="text-sm font-medium text-muted-foreground">Noble Houses</Label>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
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
                <div className="space-y-2">
                  <Label className="text-sm font-medium text-muted-foreground">
                    Commoner Families
                  </Label>
                  <Select
                    value={draft.family?.id?.toString() ?? ''}
                    onValueChange={handleFamilySelect}
                  >
                    <SelectTrigger className="w-full max-w-xs">
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

              {families?.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No families available for this area. You may select orphan or contact staff.
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </motion.div>
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
      <CardHeader className="p-3">
        <CardTitle className="text-sm">{family.name}</CardTitle>
      </CardHeader>
      {family.description && (
        <CardContent className="px-3 pb-3 pt-0">
          <CardDescription className="text-xs">{family.description}</CardDescription>
        </CardContent>
      )}
    </Card>
  );
}
