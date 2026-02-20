/**
 * Stage 5: Path Selection
 *
 * Character path (class) selection for CG.
 * Paths are the narrative-focused class system - they trace a character's
 * journey toward greatness through acts, legend, and achievements.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { AnimatePresence, motion } from 'framer-motion';
import {
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Crown,
  Eye,
  Flame,
  Heart,
  type LucideIcon,
  Loader2,
  MessageCircle,
  Minus,
  Moon,
  Plus,
  Shield,
  Sparkles,
  Sun,
  Swords,
  TreePine,
  Wand2,
  Zap,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  usePaths,
  usePathSkillSuggestions,
  useSkillPointBudget,
  useSkills,
  useUpdateDraft,
} from '../queries';
import type { CharacterDraft, Path, Skill, SkillPointBudget, Specialization } from '../types';
import { TraditionPicker } from './TraditionPicker';

interface PathStageProps {
  draft: CharacterDraft;
}

// Map icon_name strings (from Django admin) to Lucide components
// Staff can use these names in the Path.icon_name field
const ICON_MAP: Record<string, LucideIcon> = {
  swords: Swords,
  eye: Eye,
  'message-circle': MessageCircle,
  'book-open': BookOpen,
  sparkles: Sparkles,
  shield: Shield,
  crown: Crown,
  flame: Flame,
  heart: Heart,
  moon: Moon,
  sun: Sun,
  'tree-pine': TreePine,
  wand2: Wand2,
  zap: Zap,
};

/** Get icon component from icon_name, with fallback to Sparkles */
function getPathIcon(iconName: string | undefined): LucideIcon {
  if (!iconName) return Sparkles;
  return ICON_MAP[iconName.toLowerCase()] || Sparkles;
}

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

/** Skills section with interactive skill point allocation */
function SkillsSection({ draft }: { draft: CharacterDraft }) {
  const { data: skills, isLoading: skillsLoading, error: skillsError } = useSkills();
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
      const initialSkills: Record<number, number> = {};
      for (const suggestion of suggestions) {
        initialSkills[suggestion.skill_id] = suggestion.suggested_value;
      }
      setSkillValues(initialSkills);
      setSpecValues({});
      initializedPathRef.current = currentPathId;
      setIsInitialized(true);
      return;
    }

    // First time initialization - use draft data if available, otherwise suggestions
    if (!isInitialized) {
      const draftSkills = draft.draft_data?.skills;
      const draftSpecs = draft.draft_data?.specializations;

      if (draftSkills && Object.keys(draftSkills).length > 0) {
        // Convert string keys to numbers
        const numericSkills: Record<number, number> = {};
        for (const [key, value] of Object.entries(draftSkills)) {
          numericSkills[parseInt(key, 10)] = value as number;
        }
        setSkillValues(numericSkills);

        if (draftSpecs) {
          const numericSpecs: Record<number, number> = {};
          for (const [key, value] of Object.entries(draftSpecs)) {
            numericSpecs[parseInt(key, 10)] = value as number;
          }
          setSpecValues(numericSpecs);
        }
      } else if (suggestions.length > 0) {
        // Initialize from path suggestions
        const initialSkills: Record<number, number> = {};
        for (const suggestion of suggestions) {
          initialSkills[suggestion.skill_id] = suggestion.suggested_value;
        }
        setSkillValues(initialSkills);
        setSpecValues({});
      }

      initializedPathRef.current = currentPathId;
      setIsInitialized(true);
    }
  }, [
    skills,
    suggestions,
    draft.draft_data?.skills,
    draft.draft_data?.specializations,
    draft.selected_path,
    isInitialized,
  ]);

  // Debounced save to backend
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

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
              ...draft.draft_data,
              skills: skillsData,
              specializations: specsData,
            },
          },
        });
      }, 300);
    },
    [draft.id, draft.draft_data, updateDraft]
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
        <h3 className="theme-heading text-xl font-semibold">Skill Allocation</h3>
        <p className="mt-1 text-muted-foreground">
          Allocate your skill points. Your path suggests a starting distribution, but you can freely
          redistribute all points. Specializations unlock at 30 points in a skill.
        </p>
      </div>

      {/* Skill Points Header */}
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
              <div className="space-y-2">
                {categorySkills.map((skill) => {
                  const skillValue = skillValues[skill.id] || 0;
                  const showSpecs =
                    skill.specializations.length > 0 &&
                    skillValue >= budget.specialization_unlock_threshold;

                  return (
                    <div key={skill.id} className="space-y-2">
                      <SkillRow
                        skill={skill}
                        value={skillValue}
                        onChange={(newValue) => handleSkillChange(skill.id, newValue, skill)}
                        maxValue={budget.max_skill_value}
                        canIncrease={canIncrease}
                      />
                      {showSpecs && (
                        <div className="space-y-2">
                          {skill.specializations.map((spec) => (
                            <SpecializationRow
                              key={spec.id}
                              spec={spec}
                              value={specValues[spec.id] || 0}
                              onChange={(newValue) => handleSpecChange(spec.id, newValue)}
                              maxValue={budget.max_specialization_value}
                              canIncrease={canIncrease}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/** Sticky sidebar showing full path details on hover */
function PathDetailPanel({ path }: { path: Path | null }) {
  if (!path) {
    return (
      <Card className="bg-muted/30">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Hover over a path to see its full description.
        </CardContent>
      </Card>
    );
  }

  const Icon = getPathIcon(path.icon_name);

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={path.id}
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -10 }}
        transition={{ duration: 0.25 }}
      >
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
                <Icon className="h-5 w-5" />
              </div>
              <CardTitle className="text-lg">{path.name}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">
              {path.description}
            </p>
            {path.aspects.length > 0 && (
              <div>
                <div className="mb-2 text-sm font-medium">Aspects</div>
                <div className="flex flex-wrap gap-1">
                  {path.aspects.map((aspect) => (
                    <span
                      key={aspect}
                      className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                    >
                      {aspect}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}

export function PathStage({ draft }: PathStageProps) {
  const { data: paths, isLoading, error } = usePaths();
  const updateDraft = useUpdateDraft();
  const [hoveredPath, setHoveredPath] = useState<Path | null>(null);

  const handleSelectPath = (path: Path) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_path_id: path.id,
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
        Failed to load paths. Please try again.
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="theme-heading text-2xl font-bold">Choose Your Path</h2>
        <p className="mt-2 text-muted-foreground">
          Your path defines your character's approach to the world - how they solve problems, face
          challenges, and pursue their goals. As you progress, your path will evolve and branch into
          more specialized directions.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* Path cards */}
        <div className="grid gap-4 sm:grid-cols-2">
          {paths?.map((path) => {
            const isSelected = draft.selected_path?.id === path.id;
            const Icon = getPathIcon(path.icon_name);

            return (
              <Card
                key={path.id}
                className={cn(
                  'relative cursor-pointer transition-all hover:shadow-md',
                  isSelected && 'ring-2 ring-primary',
                  hoveredPath?.id === path.id && !isSelected && 'ring-1 ring-primary/30'
                )}
                onClick={() => handleSelectPath(path)}
                onMouseEnter={() => setHoveredPath(path)}
                onMouseLeave={() => setHoveredPath(null)}
              >
                {isSelected && (
                  <div className="absolute right-2 top-2">
                    <CheckCircle2 className="h-5 w-5 text-primary" />
                  </div>
                )}
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        'flex h-10 w-10 items-center justify-center rounded-lg',
                        isSelected ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
                      )}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <CardTitle className="text-lg">{path.name}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="line-clamp-3">{path.description}</CardDescription>
                  {path.aspects.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {path.aspects.map((aspect) => (
                        <span
                          key={aspect}
                          className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                        >
                          {aspect}
                        </span>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Sidebar: Path detail panel (desktop only) */}
        <div className="hidden lg:block">
          <div className="sticky top-4">
            <PathDetailPanel path={hoveredPath ?? draft.selected_path ?? null} />
          </div>
        </div>
      </div>

      {paths?.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          No paths are currently available for selection.
        </div>
      )}

      {draft.selected_path && (
        <Card className="border-primary/50 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-lg">Selected: {draft.selected_path.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{draft.selected_path.description}</p>
          </CardContent>
        </Card>
      )}

      {/* Tradition Selection - appears after path selection */}
      {draft.selected_path && draft.selected_beginnings && (
        <div className="mt-8 border-t pt-8">
          <TraditionPicker draft={draft} beginningId={draft.selected_beginnings.id} />
        </div>
      )}

      {/* Skills Section - appears after path selection */}
      {draft.selected_path && (
        <div className="mt-8 border-t pt-8">
          <SkillsSection draft={draft} />
        </div>
      )}
    </motion.div>
  );
}
