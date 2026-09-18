/**
 * Abilities (#3898) — attributes and skills, in a folding band on the front.
 *
 * These are instruments: a player operates them rather than reads them, so they keep
 * the UI sans and tabular figures while everything around them is Garamond. The band
 * puts them one fold away on the page the player opens most, instead of a tab of their
 * own — Dan's call, on the grounds that the numbers are the thing you check, not the
 * thing you visit.
 *
 * Server-gated: `stats`/`skills` arrive empty when the viewer's access does not meet
 * `stats_visibility`/`skills_visibility`, and the caller drops the whole band then.
 * Neither this component nor its caller can tell "hidden" from "none" — and neither
 * can the response, which is why the band simply is not there either way.
 *
 * Stat values arrive on the single-digit display scale already (ADR-0193).
 */

import type { CharacterSheetSkill } from '@/character_sheets/api';
import { Band, Ledger } from './primitives';

function capitalize(word: string): string {
  return word.length === 0 ? word : word[0].toUpperCase() + word.slice(1);
}

interface AbilitiesBandProps {
  stats: Record<string, number>;
  skills: CharacterSheetSkill[];
}

export function AbilitiesBand({ stats, skills }: AbilitiesBandProps) {
  const statEntries = Object.entries(stats);
  const breakthroughs = skills.filter((entry) => entry.at_boundary);

  return (
    <Band title="Abilities" note="Yours, unless you open them to friends or everyone.">
      <div className="refsheet-columns-even">
        {statEntries.length > 0 && (
          <div className="flex flex-col gap-2">
            <div className="refsheet-stat-grid refsheet-instrument" data-testid="stats-grid">
              {statEntries.map(([name, value]) => (
                <div key={name} className="refsheet-stat">
                  <span className="refsheet-stat-name">{capitalize(name)}</span>
                  <span className="refsheet-stat-value">{value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {skills.length > 0 && (
          <div className="flex flex-col gap-2">
            <div className="refsheet-skills refsheet-instrument" data-testid="skills-list">
              {skills.map((entry) => (
                <div key={entry.skill.id} className="refsheet-skill" data-testid="skill-row">
                  <div className="refsheet-skill-row">
                    <span>{capitalize(entry.skill.name)}</span>
                    <span className="refsheet-stat-value">{entry.value}</span>
                  </div>
                  {entry.specializations.map((spec) => (
                    <span key={spec.id} className="refsheet-skill-spec">
                      {spec.name} {spec.value}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      {breakthroughs.length > 0 && (
        <div className="pt-3">
          <Ledger>
            {breakthroughs.map((entry) => capitalize(entry.skill.name)).join(', ')}
            {breakthroughs.length === 1 ? ' is ' : ' are '}
            ready to break through.
          </Ledger>
        </div>
      )}
    </Band>
  );
}
