/**
 * ActorSheetSection (#3621): the three answers, the goals by horizon, the enemy as its
 * public line (the full row for the owner, staff and the assigned GM), and the
 * Introductions. Renders nothing at all when the character wrote none of it, so an
 * original character who skipped the leaf shows no empty block.
 */

import { Badge } from '@/components/ui/badge';
import type {
  CharacterSheetActorSheet,
  CharacterSheetEnemy,
  CharacterSheetIntroduction,
} from '../api';

interface GoalRow {
  domain: string;
  horizon: string;
  ordinal: number;
  points: number;
  notes: string;
}

interface ActorSheetSectionProps {
  block: CharacterSheetActorSheet;
  /** The sheet's goals section, already filtered by the goals visibility tier. */
  goals: GoalRow[];
}

const DEGREE_LABELS: Record<string, string> = {
  annoyed: 'wants them annoyed',
  thwarted: 'wants them thwarted',
  ruined: 'wants them ruined',
  destroy: 'will relentlessly try to destroy them',
};

const REACH_LABELS: Record<string, string> = {
  household: 'a household',
  house: 'a house or company',
  society: 'a society or church',
  realm: 'a realm',
};

const INSTITUTION: Record<CharacterSheetIntroduction['kind'], string> = {
  first_journal: 'The Great Archive of Vellichor',
  application: 'Shroudwatch Academy',
  whispers: 'rumors of deeds and misdeeds',
};

function enemyRowText(enemy: CharacterSheetEnemy): string {
  const scale =
    enemy.kind === 'group'
      ? (REACH_LABELS[enemy.reach] ?? 'unplaced')
      : enemy.power_tier || 'unrated';
  const status = enemy.status === 'placed' ? 'placed' : 'pending staff placement';
  return `${enemy.name || 'Unnamed'}, ${enemy.kind === 'group' ? 'a group' : 'a person'} (${scale}), ${
    DEGREE_LABELS[enemy.degree] ?? enemy.degree
  }, awards ${enemy.price}, ${status}`;
}

export function ActorSheetSection({ block, goals }: ActorSheetSectionProps) {
  const rows: Array<{ label: string; value: string }> = [
    { label: 'Would never', value: block.never_do },
    { label: 'Protects at all costs', value: block.protect },
    { label: 'Deathly afraid of', value: block.fear },
  ].filter((row) => row.value.trim() !== '');
  const shortTerm = goals.filter((g) => g.horizon === 'short_term');
  const longTerm = goals.filter((g) => g.horizon === 'long_term');
  const hasAnything =
    rows.length > 0 ||
    goals.length > 0 ||
    block.enemy_public_line !== '' ||
    block.enemy !== null ||
    block.introductions.length > 0;
  if (!hasAnything) return null;

  return (
    <section data-testid="actor-sheet-section" className="space-y-3">
      <h3 className="text-xl font-semibold">Actor&apos;s sheet</h3>
      <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[12rem_1fr]">
        {rows.map((row) => (
          <div key={row.label} className="contents">
            <dt className="text-sm text-muted-foreground">{row.label}</dt>
            <dd className="m-0">{row.value}</dd>
          </div>
        ))}
        {shortTerm.length > 0 && (
          <div className="contents">
            <dt className="text-sm text-muted-foreground">Short term goals</dt>
            <dd className="m-0">
              {shortTerm.map((g) => (
                <div key={`${g.horizon}-${g.ordinal}`}>
                  {g.ordinal}. {g.notes || g.domain}
                </div>
              ))}
            </dd>
          </div>
        )}
        {longTerm.length > 0 && (
          <div className="contents">
            <dt className="text-sm text-muted-foreground">Long term goals</dt>
            <dd className="m-0">
              {longTerm.map((g) => (
                <div key={`${g.horizon}-${g.ordinal}`}>
                  {g.ordinal}. {g.notes || g.domain}
                </div>
              ))}
            </dd>
          </div>
        )}
        {block.enemy_public_line !== '' && (
          <div className="contents">
            <dt className="text-sm text-muted-foreground">Against them</dt>
            <dd className="m-0">{block.enemy_public_line}</dd>
          </div>
        )}
        {block.enemy && (
          <div className="contents" data-testid="actor-sheet-enemy-row">
            <dt className="text-sm text-muted-foreground">Enemy (yours, staff and GM only)</dt>
            <dd className="m-0">
              {enemyRowText(block.enemy)}
              {block.enemy.why && (
                <p className="text-sm text-muted-foreground">{block.enemy.why}</p>
              )}
            </dd>
          </div>
        )}
      </dl>
      {block.introductions.map((entry) => (
        <div key={entry.id} className="border-t pt-3" data-testid="actor-sheet-introduction">
          <h4 className="font-medium">
            {entry.title} <Badge variant="outline">{INSTITUTION[entry.kind]}</Badge>
          </h4>
          <p className="whitespace-pre-wrap text-sm">{entry.body}</p>
        </div>
      ))}
    </section>
  );
}
