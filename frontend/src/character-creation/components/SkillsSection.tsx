/**
 * Skills allocation section for the Attributes & Skills stage.
 *
 * Extracted from PathStage (#2426 Task 9 stage restructure) — skills now live
 * alongside primary attributes rather than under Path. Consumes `draft` only.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { ChevronRight, Loader2, Minus, Plus } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  useCGExplanations,
  usePathSkillSuggestions,
  useSkillPointBudget,
  useSkills,
  useUpdateDraft,
} from '../queries';
import type {
  CharacterDraft,
  PathSkillSuggestion,
  Skill,
  SkillPointBudget,
  Specialization,
} from '../types';

/** Skill points header showing total, spent, and remaining */
function SkillPointsHeader({ budget, spent }: { budget: SkillPointBudget; spent: number }) {
  const remaining = budget.total_points - spent;
  const isOverBudget = remaining < 0;
  const isFullyAllocated = remaining === 0;

  return (
    <Card className="bg-muted/50">
      <CardContent className="pt-4">
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold">{budget.total_points}</div>
            <div className="text-xs text-muted-foreground">Skill Points</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{spent}</div>
            <div className="text-xs text-muted-foreground">Spent</div>
          </div>
          <div>
            <div
              className={cn(
                'text-2xl font-bold',
                isOverBudget && 'text-destructive',
                isFullyAllocated && 'text-green-600'
              )}
            >
              {remaining}
            </div>
            <div className="text-xs text-muted-foreground">Remaining</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** Single skill row with +/- controls */
function SkillRow({
  skill,
  value,
  onChange,
  maxValue,
  canIncrease,
}: {
  skill: Skill;
  value: number;
  onChange: (newValue: number) => void;
  maxValue: number;
  canIncrease: boolean;
}) {
  const canDecrease = value > 0;
  const canIncreaseValue = canIncrease && value < maxValue;

  return (
    <div className="flex items-center justify-between rounded-lg border p-3">
      <div className="flex-1">
        <div className="font-medium">{skill.name}</div>
        {skill.tooltip && <div className="text-xs text-muted-foreground">{skill.tooltip}</div>}
      </div>
      <div className="ml-4 flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          disabled={!canDecrease}
          onClick={() => onChange(value - 10)}
        >
          <Minus className="h-4 w-4" />
        </Button>
        <span className="w-8 text-center font-mono text-lg font-semibold">{value}</span>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          disabled={!canIncreaseValue}
          onClick={() => onChange(value + 10)}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

/** Specialization row with +/- controls (indented under parent skill) */
function SpecializationRow({
  spec,
  value,
  onChange,
  maxValue,
  canIncrease,
}: {
  spec: Specialization;
  value: number;
  onChange: (newValue: number) => void;
  maxValue: number;
  canIncrease: boolean;
}) {
  const canDecrease = value > 0;
  const canIncreaseValue = canIncrease && value < maxValue;

  return (
    <div className="ml-6 flex items-center justify-between rounded-lg border border-dashed bg-muted/30 p-3">
      <div className="flex flex-1 items-center gap-2">
        <ChevronRight className="h-4 w-4 text-muted-foreground" />
        <div>
          <div className="text-sm font-medium">{spec.name}</div>
          {spec.tooltip && <div className="text-xs text-muted-foreground">{spec.tooltip}</div>}
        </div>
      </div>
      <div className="ml-4 flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          className="h-7 w-7"
          disabled={!canDecrease}
          onClick={() => onChange(value - 10)}
        >
          <Minus className="h-3 w-3" />
        </Button>
        <span className="w-8 text-center font-mono font-semibold">{value}</span>
        <Button
          variant="outline"
          size="icon"
          className="h-7 w-7"
          disabled={!canIncreaseValue}
          onClick={() => onChange(value + 10)}
        >
          <Plus className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}

/**
 * Build a skill-value map from a path's suggested starting values.
 */
function skillsFromSuggestions(suggestions: PathSkillSuggestion[]): Record<number, number> {
  const initialSkills: Record<number, number> = {};
  for (const suggestion of suggestions) {
    initialSkills[suggestion.skill_id] = suggestion.suggested_value;
  }
  return initialSkills;
}

/**
 * Convert a DRF-style `Record<string, number>` (string keys from JSON) to the
 * numeric-keyed map the UI uses internally. Returns `null` for an empty input.
 */
function toNumericMap(values: Record<string, number> | undefined): Record<number, number> | null {
  if (!values) return null;
  const numeric: Record<number, number> = {};
  for (const [key, value] of Object.entries(values)) {
    numeric[parseInt(key, 10)] = value as number;
  }
  return Object.keys(numeric).length > 0 ? numeric : null;
}

/**
 * Accordion panel listing a skill's specializations, gated by the
 * specialization-unlock threshold. Extracted as its own component so the
 * `onChange` callback passed to each SpecializationRow lives at the top
 * nesting level rather than 5 functions deep (SonarCloud S2004).
 */
function SkillSpecializations({
  skill,
  skillValue,
  specValues,
  threshold,
  maxValue,
  canIncrease,
  onSpecChange,
}: {
  skill: Skill;
  skillValue: number;
  specValues: Record<number, number>;
  threshold: number;
  maxValue: number;
  canIncrease: boolean;
  onSpecChange: (specId: number, newValue: number) => void;
}) {
  return (
    <AccordionItem value={`skill-${skill.id}`} className="border-b-0">
      <AccordionTrigger className="ml-6 py-2 text-xs text-muted-foreground hover:no-underline">
        Specializations ({skill.specializations.length})
      </AccordionTrigger>
      <AccordionContent className="ml-6">
        {skillValue >= threshold ? (
          <div className="space-y-2">
            {skill.specializations.map((spec) => (
              <SpecializationRow
                key={spec.id}
                spec={spec}
                value={specValues[spec.id] || 0}
                onChange={(newValue) => onSpecChange(spec.id, newValue)}
                maxValue={maxValue}
                canIncrease={canIncrease}
              />
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Requires {threshold}+ points in {skill.name}
          </p>
        )}
      </AccordionContent>
    </AccordionItem>
  );
}

/** Skills section with interactive skill point allocation */
export function SkillsSection({ draft }: { draft: CharacterDraft }) {
  const { data: skills, isLoading: skillsLoading, error: skillsError } = useSkills();
  const { data: copy } = useCGExplanations();
  const { data: budget, isLoading: budgetLoading, error: budgetError } = useSkillPointBudget();
  const { data: suggestions } = usePathSkillSuggestions(draft.selected_path?.id);
  const updateDraft = useUpdateDraft();

  // Local state for skill and specialization values
  const [skillValues, setSkillValues] = useState<Record<number, number>>({});
  const [specValues, setSpecValues] = useState<Record<number, number>>({});
  const [isInitialized, setIsInitialized] = useState(false);

  // Track the path ID we initialized from to detect path changes
  const initializedPathRef = useRef<number | null>(null);

  // Initialize from draft_data or path suggestions, and handle path changes
  useEffect(() => {
    if (!skills || !suggestions || !draft.selected_path) return;

    const currentPathId = draft.selected_path.id;
    const pathChanged =
      initializedPathRef.current !== null && initializedPathRef.current !== currentPathId;

    // If path changed, always reset to new path's suggestions
    if (pathChanged) {
      const initialSkills = skillsFromSuggestions(suggestions);
      setSkillValues(initialSkills);
      setSpecValues({});
      // Persist the reset (2026-07 audit): the UI showed the new path's
      // suggestions but the server kept the OLD path's allocation — clicking
      // Next without touching a skill submitted data the UI never showed.
      saveToBackend(initialSkills, {});
      initializedPathRef.current = currentPathId;
      setIsInitialized(true);
      return;
    }

    // First time initialization - use draft data if available, otherwise suggestions
    if (isInitialized) return;

    const numericSkills = toNumericMap(draft.draft_data?.skills);
    if (numericSkills) {
      setSkillValues(numericSkills);
      // Preserve original behavior: set specs whenever they exist on the
      // draft (even an empty {}), converting string keys to numbers.
      if (draft.draft_data?.specializations) {
        setSpecValues(toNumericMap(draft.draft_data.specializations) ?? {});
      }
    } else if (suggestions.length > 0) {
      // Initialize from path suggestions
      setSkillValues(skillsFromSuggestions(suggestions));
      setSpecValues({});
    }

    initializedPathRef.current = currentPathId;
    setIsInitialized(true);
  }, [
    skills,
    suggestions,
    draft.draft_data?.skills,
    draft.draft_data?.specializations,
    draft.selected_path,
    isInitialized,
  ]);

  // Debounced save to backend
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const saveToBackend = useCallback(
    (newSkillValues: Record<number, number>, newSpecValues: Record<number, number>) => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }

      saveTimeoutRef.current = setTimeout(() => {
        // Convert numeric keys to string keys for JSON
        const skillsData: Record<string, number> = {};
        for (const [key, value] of Object.entries(newSkillValues)) {
          if (value > 0) {
            skillsData[key.toString()] = value;
          }
        }

        const specsData: Record<string, number> = {};
        for (const [key, value] of Object.entries(newSpecValues)) {
          if (value > 0) {
            specsData[key.toString()] = value;
          }
        }

        updateDraft.mutate({
          draftId: draft.id,
          data: {
            draft_data: {
              skills: skillsData,
              specializations: specsData,
            },
          },
        });
      }, 300);
    },
    [draft.id, updateDraft]
  );

  // Calculate total spent
  const totalSpent = useMemo(() => {
    const skillTotal = Object.values(skillValues).reduce((sum, v) => sum + v, 0);
    const specTotal = Object.values(specValues).reduce((sum, v) => sum + v, 0);
    return skillTotal + specTotal;
  }, [skillValues, specValues]);

  // Handle skill value change
  const handleSkillChange = useCallback(
    (skillId: number, newValue: number, skill: Skill) => {
      const newSkillValues = { ...skillValues, [skillId]: newValue };

      // If lowering below specialization threshold, zero out specializations
      const newSpecValues = { ...specValues };
      if (budget && newValue < budget.specialization_unlock_threshold) {
        for (const spec of skill.specializations) {
          if (newSpecValues[spec.id] > 0) {
            newSpecValues[spec.id] = 0;
          }
        }
      }

      setSkillValues(newSkillValues);
      setSpecValues(newSpecValues);
      saveToBackend(newSkillValues, newSpecValues);
    },
    [skillValues, specValues, budget, saveToBackend]
  );

  // Handle specialization value change
  const handleSpecChange = useCallback(
    (specId: number, newValue: number) => {
      const newSpecValues = { ...specValues, [specId]: newValue };
      setSpecValues(newSpecValues);
      saveToBackend(skillValues, newSpecValues);
    },
    [skillValues, specValues, saveToBackend]
  );

  if (skillsLoading || budgetLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading skills...</span>
      </div>
    );
  }

  if (skillsError || budgetError) {
    return (
      <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
        Failed to load skills data. Please try again.
      </div>
    );
  }

  if (!skills || !budget) {
    return null;
  }

  // Group skills by category
  const skillsByCategory = skills.reduce(
    (acc, skill) => {
      const cat = skill.category_display;
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(skill);
      return acc;
    },
    {} as Record<string, Skill[]>
  );

  const remaining = budget.total_points - totalSpent;
  const canIncrease = remaining >= 10;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="theme-heading text-xl font-semibold">{copy?.path_skills_heading ?? ''}</h3>
        <p className="mt-1 text-muted-foreground">{copy?.path_skills_desc ?? ''}</p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
        {/* Main content */}
        <div className="space-y-6">
          {/* Skill Points Header (inline) */}
          <SkillPointsHeader budget={budget} spent={totalSpent} />

          {/* Path Suggestions Reference */}
          {suggestions && suggestions.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">
                  {draft.selected_path?.name} Suggested Skills
                </CardTitle>
                <CardDescription>
                  Your path suggests these skills. You can freely redistribute all points.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {suggestions.map((s) => (
                    <span
                      key={s.id}
                      className="rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary"
                    >
                      {s.skill_name}: {s.suggested_value}
                    </span>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Skills by Category */}
          <div className="space-y-4">
            {Object.entries(skillsByCategory).map(([category, categorySkills]) => (
              <Card key={category}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">{category}</CardTitle>
                </CardHeader>
                <CardContent>
                  <Accordion type="multiple">
                    <div className="space-y-2">
                      {categorySkills.map((skill) => {
                        const skillValue = skillValues[skill.id] || 0;
                        const hasSpecs = skill.specializations.length > 0;

                        return (
                          <div key={skill.id}>
                            <SkillRow
                              skill={skill}
                              value={skillValue}
                              onChange={(newValue) => handleSkillChange(skill.id, newValue, skill)}
                              maxValue={budget.max_skill_value}
                              canIncrease={canIncrease}
                            />
                            {hasSpecs && (
                              <SkillSpecializations
                                skill={skill}
                                skillValue={skillValue}
                                specValues={specValues}
                                threshold={budget.specialization_unlock_threshold}
                                maxValue={budget.max_specialization_value}
                                canIncrease={canIncrease}
                                onSpecChange={handleSpecChange}
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </Accordion>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* Sticky sidebar (desktop only) */}
        <div className="hidden lg:block">
          <div className="sticky top-4 space-y-4">
            <SkillPointsHeader budget={budget} spent={totalSpent} />
            <p className="text-xs text-muted-foreground">
              Skills with {budget.specialization_unlock_threshold}+ points unlock specializations.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
