/**
 * MechanicsSection (#3042) — the character sheet's Attributes + Skills display.
 *
 * Ungated: `stats`/`skills` on the sheet payload are already visibility-filtered server-side
 * (`CharacterSheetSerializer.to_representation`, src/world/character_sheets/serializers.py —
 * `show_stats`/`show_skills` per `stats_visibility`/`skills_visibility`), returning `{}`/`[]`
 * for a viewer who isn't allowed to see them. This component only renders whatever
 * `useCharacterSheetQuery` returns — it does NOT re-implement visibility client-side, and it
 * can't distinguish "hidden" from "genuinely no data" (neither can the API response).
 *
 * Stat values arrive already converted to the single-digit display scale (÷10 from the ×10
 * internal storage, ADR-0193) — this component renders them as-is.
 */

import type { CharacterSheetSkill } from '@/character_sheets/api';
import { Badge } from '@/components/ui/badge';

interface MechanicsSectionProps {
  stats: Record<string, number>;
  skills: CharacterSheetSkill[];
}

function capitalize(word: string): string {
  return word.length === 0 ? word : word[0].toUpperCase() + word.slice(1);
}

export function MechanicsSection({ stats, skills }: MechanicsSectionProps) {
  const statEntries = Object.entries(stats);

  return (
    <>
      <section>
        <h3 className="text-xl font-semibold">Attributes</h3>
        {statEntries.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="stats-empty-state">
            No attributes shared.
          </p>
        ) : (
          <dl
            className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3 md:grid-cols-4"
            data-testid="stats-grid"
          >
            {statEntries.map(([name, value]) => (
              <div key={name} className="flex justify-between gap-2 sm:block">
                <dt className="text-sm text-muted-foreground">{capitalize(name)}</dt>
                <dd className="font-medium tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section>
        <h3 className="text-xl font-semibold">Skills</h3>
        {skills.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="skills-empty-state">
            No skills shared.
          </p>
        ) : (
          <ul className="space-y-1" data-testid="skills-list">
            {skills.map((entry) => (
              <li key={entry.skill.id} data-testid="skill-row">
                <div className="flex items-center justify-between gap-2">
                  <span>{capitalize(entry.skill.name)}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-medium tabular-nums">{entry.value}</span>
                    {entry.at_boundary && (
                      <Badge variant="outline" data-testid="skill-at-boundary">
                        Ready to break through
                      </Badge>
                    )}
                  </span>
                </div>
                {entry.specializations.length > 0 && (
                  <ul className="ml-4 text-sm text-muted-foreground">
                    {entry.specializations.map((spec) => (
                      <li key={spec.id}>
                        {spec.name} ({spec.value})
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
