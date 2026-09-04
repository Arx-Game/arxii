/**
 * Stage 10: Final Touches - Goals (#3630).
 *
 * Goals by domain in one framed instrument with the points purse at its
 * head, replacing the bespoke tracker card, info card and accordion. Each
 * goal is a row: a notes field, a points field, and a "Remove" door. "How
 * goals work" moves from an info card to the margin (Decision 8). Selections
 * are stored locally and auto-saved when navigating away.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChapterLeaf,
  Field,
  InstrumentFrame,
  InstrumentGroup,
  Marginalia,
  Note,
  RecordRail,
} from '../folio';
import { useGoalDomains } from '../goals';
import { useCGExplanations, useUpdateDraft } from '../queries';
import type { CharacterDraft, DraftGoal } from '../types';
import { Stage } from '../types';

interface FinalTouchesStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => (() => void) | void;
}

interface KeyedGoal {
  key: number;
  goal: DraftGoal;
}

const BASE_GOAL_POINTS = 30;

/**
 * Announcer text for a point change. Deliberately worded differently from the
 * ledger's "Points remaining: N of 30, over by M" so the two don't collide
 * under a single `getByText` match in tests (both are visible to the DOM at
 * once, the ledger visibly and the announcer via `.vh`).
 */
function announceText(remaining: number): string {
  return remaining < 0 ? `${Math.abs(remaining)} points over.` : `${remaining} points remain.`;
}

export function FinalTouchesStage({ draft, onRegisterBeforeLeave }: FinalTouchesStageProps) {
  const { data: domains, isLoading: domainsLoading, error: domainsError } = useGoalDomains();
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();

  const keyCounterRef = useRef(0);
  const [keyedGoals, setKeyedGoals] = useState<KeyedGoal[]>(() =>
    (draft.draft_data.goals ?? []).map((goal) => ({ key: keyCounterRef.current++, goal }))
  );
  const [announce, setAnnounce] = useState('');

  // The value actually flushed to draft_data.goals: plain DraftGoal[], no local keys.
  const goals = useMemo(() => keyedGoals.map((kg) => kg.goal), [keyedGoals]);

  const hasChangesRef = useRef(false);
  const goalsRef = useRef(goals);
  goalsRef.current = goals;

  const usedPoints = goals.reduce((sum, g) => sum + g.points, 0);
  const remaining = BASE_GOAL_POINTS - usedPoints;

  // Track changes compared to server state
  useEffect(() => {
    const draftGoals = draft.draft_data.goals ?? [];
    const hasChanges = JSON.stringify(goals) !== JSON.stringify(draftGoals);
    hasChangesRef.current = hasChanges;
  }, [goals, draft.draft_data.goals]);

  const saveGoals = useCallback(async () => {
    if (!hasChangesRef.current) return true;

    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: {
          draft_data: {
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
  }, [draft.id, updateDraft]);

  // Register beforeLeave callback
  useEffect(() => {
    if (!onRegisterBeforeLeave) return;
    // Return the unregister as cleanup (2026-07 audit): without it, an
    // unmounted stage's save closure stayed registered and re-fired on every
    // later navigation, PATCHing stale values over newer edits.
    return onRegisterBeforeLeave(saveGoals) ?? undefined;
  }, [onRegisterBeforeLeave, saveGoals]);

  const goalsForDomain = (domainId: number) =>
    keyedGoals.filter((kg) => kg.goal.domain_id === domainId);

  /** Applies a new local goal list and announces the resulting purse. */
  const applyGoals = (next: KeyedGoal[]) => {
    setKeyedGoals(next);
    const used = next.reduce((sum, kg) => sum + kg.goal.points, 0);
    setAnnounce(announceText(BASE_GOAL_POINTS - used));
  };

  const addGoal = (domainId: number) => {
    applyGoals([
      ...keyedGoals,
      { key: keyCounterRef.current++, goal: { domain_id: domainId, notes: '', points: 0 } },
    ]);
  };

  const updateGoalNotes = (key: number, notes: string) => {
    applyGoals(
      keyedGoals.map((kg) => (kg.key === key ? { key, goal: { ...kg.goal, notes } } : kg))
    );
  };

  const updateGoalPoints = (key: number, rawPoints: number) => {
    const clamped = Math.max(0, Math.min(BASE_GOAL_POINTS, rawPoints));
    applyGoals(
      keyedGoals.map((kg) => (kg.key === key ? { key, goal: { ...kg.goal, points: clamped } } : kg))
    );
  };

  const removeGoal = (key: number) => {
    applyGoals(keyedGoals.filter((kg) => kg.key !== key));
  };

  if (domainsLoading) {
    return (
      <p className="ledger-line" aria-busy="true">
        Loading goal domains…
      </p>
    );
  }

  if (domainsError) {
    return (
      <p className="ledger-line">Unable to load goal domains. Please try refreshing the page.</p>
    );
  }

  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Path', value: draft.selected_path?.name },
          {
            label: 'Goals',
            value: `${goals.length} goals, ${usedPoints} of ${BASE_GOAL_POINTS} points`,
          },
        ]}
        ledger="Stage 10 of 11"
      />
      <Marginalia id="note-finaltouches">
        <Note lead="How goals work">
          {copy?.finaltouches_how_note ?? (
            <>
              Goals are optional but recommended. During play, you can invoke a goal when making a
              check that relates to it. Your goal&apos;s point value adds as a bonus to the roll.
              You can use goals up to twice your total points per day.
            </>
          )}
        </Note>
      </Marginalia>
    </>
  );

  return (
    <ChapterLeaf
      stage={Stage.FINAL_TOUCHES}
      title={copy?.finaltouches_heading ?? 'Goals & Motivations'}
      intro={copy?.finaltouches_intro}
      aside={rail}
    >
      <span className="vh" role="status">
        {announce}
      </span>
      <InstrumentFrame
        label="Goals"
        ledger={{
          left: `${goals.length} goals across ${(domains ?? []).length} domains`,
          right: (
            <>
              Points remaining: <b>{remaining}</b> of <b>{BASE_GOAL_POINTS}</b>
              {remaining < 0 && <>, over by {Math.abs(remaining)}</>}
            </>
          ),
          over: remaining < 0,
        }}
      >
        {(domains ?? []).map((domain) => (
          <InstrumentGroup
            key={domain.id}
            title={domain.name}
            gloss={domain.description || undefined}
          >
            {goalsForDomain(domain.id).map((kg) => (
              <div className="stat-row goal-row" key={kg.key}>
                <Field id={`goal-${kg.key}-notes`} label="Goal">
                  <input
                    id={`goal-${kg.key}-notes`}
                    type="text"
                    value={kg.goal.notes}
                    onChange={(e) => updateGoalNotes(kg.key, e.target.value)}
                  />
                </Field>
                <Field id={`goal-${kg.key}-points`} label="Points">
                  <input
                    id={`goal-${kg.key}-points`}
                    type="number"
                    min={0}
                    max={BASE_GOAL_POINTS}
                    value={kg.goal.points}
                    onChange={(e) => updateGoalPoints(kg.key, parseInt(e.target.value, 10) || 0)}
                  />
                </Field>
                <button type="button" className="btn-quiet" onClick={() => removeGoal(kg.key)}>
                  Remove
                </button>
              </div>
            ))}
            <p className="ledger-line">
              <button type="button" className="btn-small" onClick={() => addGoal(domain.id)}>
                Add a goal
              </button>
            </p>
          </InstrumentGroup>
        ))}
      </InstrumentFrame>
    </ChapterLeaf>
  );
}
