/**
 * Skills allocation section for the Attributes & Skills stage.
 *
 * Extracted from PathStage (#2426 Task 9 stage restructure) — skills now live
 * alongside primary attributes rather than under Path. Consumes `draft` only.
 *
 * Presentation rebuilt for the Folio (#3540): the skill/specialization rows
 * are `StatRow` instruments inside an `InstrumentFrame`, with the purse in
 * the frame's ledger head. State and the debounced save are unchanged.
 */

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Loader2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { InstrumentFrame, StatRow } from '../folio';
import {
  useCGExplanations,
  usePathSkillSuggestions,
  useSkillPointBudget,
  useSkills,
  useUpdateDraft,
} from '../queries';
import type { CharacterDraft, PathSkillSuggestion, Skill, Specialization } from '../types';

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
 * `onChange` callback passed to each spec's StatRow lives at the top
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
      <AccordionTrigger className="quiet-link">
        Specializations ({skill.specializations.length})
      </AccordionTrigger>
      <AccordionContent>
        {skillValue >= threshold ? (
          skill.specializations.map((spec: Specialization) => {
            const value = specValues[spec.id] || 0;
            const canIncreaseValue = canIncrease && value < maxValue;
            return (
              <StatRow
                key={spec.id}
                id={`lbl-skill-spec-${spec.id}`}
                name={spec.name}
                sub={spec.tooltip}
                value={value}
                max={maxValue}
                step={10}
                onChange={(newValue) => onSpecChange(spec.id, newValue)}
                canDecrease={value > 0}
                canIncrease={canIncreaseValue}
                spec
              />
            );
          })
        ) : (
          <p className="ledger-line">
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
    return <p className="ledger-line">Failed to load skills data. Please try again.</p>;
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
  const visibleSkills = skills;

  return (
    <div>
      {copy?.path_skills_desc && (
        <div className="leaf-body">
          <p>{copy.path_skills_desc}</p>
        </div>
      )}

      {suggestions && suggestions.length > 0 && (
        // PLACEHOLDER: Apostate rewrite
        <p className="ledger-line">
          {draft.selected_path?.name} suggested skills:{' '}
          {suggestions.map((s) => `${s.skill_name} ${s.suggested_value}`).join(', ')}. You can
          freely redistribute all points.
        </p>
      )}

      <InstrumentFrame
        label="Skills"
        ledger={{
          left: `${visibleSkills.length} of ${skills.length} skills shown`,
          right: (
            <>
              Skill points remaining: <b>{remaining}</b> of <b>{budget.total_points}</b>
            </>
          ),
          over: remaining < 0,
        }}
      >
        {Object.entries(skillsByCategory).map(([category, categorySkills]) => (
          <div key={category} className="instr-group">
            <div className="instr-group-h">{category}</div>
            <Accordion type="multiple">
              {categorySkills.map((skill: Skill) => {
                const skillValue = skillValues[skill.id] || 0;
                const hasSpecs = skill.specializations.length > 0;
                const canIncreaseValue = canIncrease && skillValue < budget.max_skill_value;

                return (
                  <div key={skill.id}>
                    <StatRow
                      id={`lbl-skill-${skill.id}`}
                      name={skill.name}
                      sub={skill.tooltip}
                      value={skillValue}
                      max={budget.max_skill_value}
                      step={10}
                      onChange={(newValue) => handleSkillChange(skill.id, newValue, skill)}
                      canDecrease={skillValue > 0}
                      canIncrease={canIncreaseValue}
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
            </Accordion>
          </div>
        ))}
      </InstrumentFrame>
    </div>
  );
}
