/**
 * Final Touches Stage - Goals
 *
 * Players define their character's goals and motivations. Goals provide
 * bonuses when making checks that align with the character's driving desires.
 *
 * Selections are stored locally and auto-saved when navigating away.
 */

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { motion } from 'framer-motion';
import { AlertCircle, Info, Loader2, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useGoalDomains } from '../goals';
import { useUpdateDraft } from '../queries';
import type { CharacterDraft, DraftGoal } from '../types';

interface FinalTouchesStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => void;
}

const BASE_GOAL_POINTS = 30;

export function FinalTouchesStage({ draft, onRegisterBeforeLeave }: FinalTouchesStageProps) {
  const { data: domains, isLoading: domainsLoading, error: domainsError } = useGoalDomains();
  const updateDraft = useUpdateDraft();

  const [goals, setGoals] = useState<DraftGoal[]>(draft.draft_data.goals ?? []);
  const [openDomains, setOpenDomains] = useState<string[]>([]);

  const hasChangesRef = useRef(false);
  const goalsRef = useRef(goals);
  goalsRef.current = goals;

  const totalPoints = BASE_GOAL_POINTS;
  const usedPoints = goals.reduce((sum, g) => sum + g.points, 0);
  const remainingPoints = totalPoints - usedPoints;

  // Track changes compared to server state
  useEffect(() => {
    const draftGoals = draft.draft_data.goals ?? [];
    const hasChanges = JSON.stringify(goals) !== JSON.stringify(draftGoals);
    hasChangesRef.current = hasChanges;
  }, [goals, draft.draft_data.goals]);

  // Initialize open domains based on which have goals
  useEffect(() => {
    if (domains && goals.length > 0) {
      const domainIdsWithGoals = new Set(goals.map((g) => g.domain_id));
      const domainKeys = domains
        .filter((d) => domainIdsWithGoals.has(d.id))
        .map((d) => d.name.toLowerCase());
      setOpenDomains(domainKeys);
    }
  }, [domains, goals]);

  const saveGoals = useCallback(async () => {
    if (!hasChangesRef.current) return true;

    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: {
          draft_data: {
            ...draft.draft_data,
            goals: goalsRef.current,
          },
        },
      });
      hasChangesRef.current = false;
      return true;
    } catch (error) {
      console.error('[FinalTouches] Auto-save failed:', error);
      const discard = window.confirm('Failed to save goals. Discard changes and continue anyway?');
      return discard;
    }
  }, [draft.id, draft.draft_data, updateDraft]);

  // Register beforeLeave callback
  useEffect(() => {
    if (onRegisterBeforeLeave) {
      onRegisterBeforeLeave(saveGoals);
    }
  }, [onRegisterBeforeLeave, saveGoals]);

  const getGoalsForDomain = (domainId: number) => goals.filter((g) => g.domain_id === domainId);

  const addGoal = (domainId: number, domainName: string) => {
    setGoals([...goals, { domain_id: domainId, notes: '', points: 0 }]);
    // Auto-open the domain when adding a goal
    const domainKey = domainName.toLowerCase();
    if (!openDomains.includes(domainKey)) {
      setOpenDomains([...openDomains, domainKey]);
    }
  };

  const updateGoal = (index: number, updates: Partial<DraftGoal>) => {
    const newGoals = [...goals];
    // Clamp points to valid range
    if (updates.points !== undefined) {
      updates.points = Math.max(0, Math.min(totalPoints, updates.points));
    }
    newGoals[index] = { ...newGoals[index], ...updates };
    setGoals(newGoals);
  };

  const removeGoal = (index: number) => {
    setGoals(goals.filter((_, i) => i !== index));
  };

  const findGoalIndex = (domainId: number, localIndex: number) => {
    let count = 0;
    for (let i = 0; i < goals.length; i++) {
      if (goals[i].domain_id === domainId) {
        if (count === localIndex) return i;
        count++;
      }
    }
    return -1;
  };

  if (domainsLoading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="space-y-6"
      >
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </motion.div>
    );
  }

  if (domainsError) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="space-y-6"
      >
        <Card className="border-destructive bg-destructive/10">
          <CardContent className="pt-6">
            <div className="flex gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-destructive" />
              <div className="text-sm">
                <p className="mb-1 font-medium text-destructive">Failed to load goal domains</p>
                <p className="text-muted-foreground">
                  Unable to load goal domains. Please try refreshing the page.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="space-y-6"
    >
      <div>
        <h2 className="theme-heading text-2xl font-bold">Final Touches</h2>
        <p className="mt-2 text-muted-foreground">
          Define your character's goals and motivations. Goals provide bonuses when making checks
          that align with your character's driving desires.
        </p>
      </div>

      {/* Points tracker */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Goal Points</p>
              <p className="text-2xl font-bold">
                {usedPoints} / {totalPoints}
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm text-muted-foreground">Remaining</p>
              <p className={`text-2xl font-bold ${remainingPoints < 0 ? 'text-destructive' : ''}`}>
                {remainingPoints}
              </p>
            </div>
          </div>
          {remainingPoints < 0 && (
            <p className="mt-2 text-sm text-destructive">
              You've allocated more points than available. Remove some goals or reduce points.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Info box */}
      <Card className="border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950">
        <CardContent className="pt-6">
          <div className="flex gap-3">
            <Info className="mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600 dark:text-blue-400" />
            <div className="text-sm text-blue-800 dark:text-blue-200">
              <p className="mb-1 font-medium">How Goals Work</p>
              <p>
                Goals are optional but recommended. During play, you can invoke a goal when making a
                check that relates to it. Your goal's point value adds as a bonus to the roll. You
                can use goals up to twice your total points per day.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Domain accordions */}
      <Accordion
        type="multiple"
        value={openDomains}
        onValueChange={setOpenDomains}
        className="space-y-4"
      >
        {domains?.map((domain) => {
          const domainGoals = getGoalsForDomain(domain.id);
          const domainPoints = domainGoals.reduce((sum, g) => sum + g.points, 0);
          const domainKey = domain.name.toLowerCase();

          return (
            <AccordionItem
              key={domain.id}
              value={domainKey}
              className="rounded-lg border bg-card px-4"
            >
              <AccordionTrigger className="hover:no-underline">
                <div className="flex w-full items-center justify-between pr-2">
                  <div className="text-left">
                    <span className="text-lg font-semibold">{domain.name}</span>
                    <p className="mt-1 text-sm text-muted-foreground">{domain.description}</p>
                  </div>
                  {domainGoals.length > 0 && (
                    <Badge variant="secondary" className="ml-4">
                      {domainPoints} pts
                    </Badge>
                  )}
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-4 pb-2">
                  {domainGoals.map((goal, localIndex) => {
                    const globalIndex = findGoalIndex(domain.id, localIndex);
                    return (
                      <div key={localIndex} className="flex items-start gap-3">
                        <Input
                          placeholder="Describe your goal..."
                          value={goal.notes}
                          onChange={(e) => updateGoal(globalIndex, { notes: e.target.value })}
                          className="flex-1"
                        />
                        <Input
                          type="number"
                          min={0}
                          max={totalPoints}
                          value={goal.points}
                          onChange={(e) =>
                            updateGoal(globalIndex, { points: parseInt(e.target.value) || 0 })
                          }
                          className="w-20"
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => removeGoal(globalIndex)}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    );
                  })}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => addGoal(domain.id, domain.name)}
                    className="w-full"
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    Add Goal
                  </Button>
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </motion.div>
  );
}
