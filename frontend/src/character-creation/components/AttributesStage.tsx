/**
 * Stage 7: Attributes & Skills (#3540).
 *
 * Twelve statistics in a framed instrument with the purse at its head, then
 * the skills frame. A statistic's name is a door: pressing it writes what the
 * number governs into the margin (replacing the hover card). The record rail
 * lists the spend; it characterises nothing (Decision 8).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChapterLeaf,
  InstrumentFrame,
  InstrumentGroup,
  Marginalia,
  RecordRail,
  StatRow,
  stageEyebrow,
} from '../folio';
import { useCGExplanations, useStatDefinitions, useUpdateDraft } from '../queries';
import { getDefaultStats, Stage } from '../types';
import type { CharacterDraft, Stats } from '../types';
import { SkillsSection } from './SkillsSection';

interface AttributesStageProps {
  draft: CharacterDraft;
}

const STAT_MIN = 10;
const STAT_MAX = 50;
/** One stat point raises a statistic by 10. */
const STAT_STEP = 10;

/** Why the raise button is disabled, if it is; `undefined` when it isn't. */
function increaseTitleFor(atCap: boolean, out: boolean): string | undefined {
  if (atCap) return `At ${STAT_MAX}, the most it can be`;
  if (out) return 'No points remain; lower another to raise this one';
  return undefined;
}

/** Stat categories. They carried a gloss each ("the body", "the company"); the owner had
 *  them removed as unnecessary (#5223, 2026-11-20). */
const STAT_CATEGORIES: { label: string; stats: (keyof Stats)[] }[] = [
  { label: 'Physical', stats: ['strength', 'agility', 'stamina'] },
  { label: 'Social', stats: ['charm', 'presence', 'composure'] },
  { label: 'Mental', stats: ['intellect', 'wits', 'stability'] },
  { label: 'Meta', stats: ['luck', 'perception', 'willpower'] },
];

export function AttributesStage({ draft }: AttributesStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: statDefinitions, isLoading } = useStatDefinitions();
  const stats: Stats = draft.draft_data.stats ?? getDefaultStats();
  const remaining = draft.stats_points_remaining;
  const budget = draft.stats_budget;
  const bonuses = draft.stat_bonuses ?? {};
  const [why, setWhy] = useState<string | null>(null);
  const [announce, setAnnounce] = useState('');
  // The Skills section owns its own allocation; it reports its totals for the side panel's
  // "Skills" row (#5223).
  const [skillPoints, setSkillPoints] = useState<{ spent: number; total: number } | null>(null);
  const reportSkillPoints = useCallback((spent: number, total: number) => {
    setSkillPoints((prev) =>
      prev && prev.spent === spent && prev.total === total ? prev : { spent, total }
    );
  }, []);

  const descriptions = useMemo(
    () => Object.fromEntries((statDefinitions ?? []).map((s) => [s.name, s.description])),
    [statDefinitions]
  );

  // The spread on screen is the spread the draft holds (#5198). A draft that has never
  // saved its statistics shows the even spread with no points left, and the server counted
  // that as twelve missing statistics until a button was pressed, so a player who wanted
  // the even spread had to lower one and raise it again. Opening the stage saves what it
  // shows, once: the ref stops a second save while the first is in flight, and the saved
  // draft stops any after it.
  const hasSavedStats = draft.draft_data.stats != null;
  const savedDefaultsFor = useRef<number | null>(null);
  const saveStats = updateDraft.mutate;
  useEffect(() => {
    if (hasSavedStats || savedDefaultsFor.current === draft.id) return;
    savedDefaultsFor.current = draft.id;
    saveStats({ draftId: draft.id, data: { draft_data: { stats: getDefaultStats() } } });
  }, [hasSavedStats, draft.id, saveStats]);

  const change = (stat: keyof Stats, value: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { stats: { ...stats, [stat]: value } } },
    });
    const left = remaining - (value - stats[stat]);
    setAnnounce(`${stat} ${value}. ${left} points remain.`);
  };

  if (isLoading)
    return (
      <p className="ledger-line" aria-busy="true">
        Loading statistics…
      </p>
    );

  const spent = budget - remaining;
  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Beginning', value: draft.selected_beginnings?.name },
          { label: 'Species', value: draft.selected_species?.name },
          { label: 'Family', value: draft.family?.name },
          { label: 'Path', value: draft.selected_path?.name },
          { label: 'Tradition', value: draft.selected_tradition?.name },
          { label: 'Statistics', value: `${spent} of ${budget} spent` },
          ...(skillPoints
            ? [{ label: 'Skills', value: `${skillPoints.spent} of ${skillPoints.total} spent` }]
            : []),
        ]}
        ledger={stageEyebrow(draft.current_stage)}
      />
      <Marginalia id="note-why">
        <span className="note" id="why-note" role="status">
          {why ? (
            <>
              <b className="capitalize">On {why}.</b> {descriptions[why] ?? ''}
            </>
          ) : (
            <>
              <b>Statistics.</b> Select a statistic’s name to read what it governs.
            </>
          )}
        </span>
      </Marginalia>
    </>
  );

  return (
    <ChapterLeaf
      stage={Stage.ATTRIBUTES}
      title="Attributes & Skills"
      intro={copy?.attributes_intro}
      aside={rail}
    >
      <span className="vh" role="status">
        {announce}
      </span>
      <h2 className="section-h" id="scores">
        {copy?.attributes_heading ?? 'Attribute Scores'}
      </h2>
      <InstrumentFrame
        label="Statistics"
        ledger={{
          left: `Min ${STAT_MIN}, Max ${STAT_MAX}`,
          right: (
            <>
              Points remaining: <b>{remaining}</b> of <b>{budget}</b>
              {remaining < 0 && <>, over by {Math.abs(remaining)}</>}
            </>
          ),
          over: remaining < 0,
        }}
      >
        {STAT_CATEGORIES.map((cat) => (
          <InstrumentGroup key={cat.label} title={cat.label}>
            {cat.stats.map((stat) => {
              const value = stats[stat];
              const atCap = value >= STAT_MAX;
              const out = remaining < STAT_STEP;
              return (
                <StatRow
                  key={stat}
                  id={`lbl-${stat}`}
                  name={stat}
                  value={value}
                  bonus={bonuses[stat] || undefined}
                  step={STAT_STEP}
                  onChange={(v) => change(stat, v)}
                  canDecrease={value > STAT_MIN}
                  canIncrease={!atCap && !out}
                  increaseTitle={increaseTitleFor(atCap, out)}
                  // Pressing a name shows what it governs in the side panel, and hovering
                  // shows the same text. No line opens under the row (#5223).
                  onWhy={() => setWhy(stat)}
                  whyOpen={why === stat}
                  whyTitle={descriptions[stat]}
                />
              );
            })}
          </InstrumentGroup>
        ))}
      </InstrumentFrame>

      {draft.selected_path && (
        <>
          <h2 className="section-h" id="skills">
            Skills
          </h2>
          <SkillsSection draft={draft} onPointsChange={reportSkillPoints} />
        </>
      )}
    </ChapterLeaf>
  );
}
