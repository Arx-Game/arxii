/**
 * StandoffSummaryCard (#4354): the public standoff summary an onlooker sees
 * (a viewer in the scene who is neither in the encounter nor its GM). It shows
 * each group's size and state only; the revealed cause and drives stay with the
 * party.
 */

import type { components } from '@/generated/api';

import { MoraleStateChip } from './MoraleStateChip';

type StandoffSummary = components['schemas']['StandoffSummary'];

export function StandoffSummaryCard({ summary }: { summary: StandoffSummary }) {
  return (
    <div
      className="flex flex-col gap-3 rounded-md border border-border bg-muted/30 p-3"
      data-testid="standoff-summary-card"
    >
      <h3 className="font-display text-sm font-bold">
        Standoff <span className="font-normal text-muted-foreground">at {summary.place}</span>
      </h3>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
            <th className="py-1 pr-2 font-medium">Group</th>
            <th className="py-1 pr-2 font-medium">Count</th>
            <th className="py-1 font-medium">State</th>
          </tr>
        </thead>
        <tbody>
          {summary.groups.map((g) => (
            <tr key={g.group_id} className="border-t border-border align-top">
              <td className="py-1 pr-2">{g.name}</td>
              <td className="py-1 pr-2">{g.member_count}</td>
              <td className="py-1">
                <span className="flex flex-wrap items-center gap-1">
                  <span>{g.state}</span>
                  {g.emboldened && (
                    <span className="rounded bg-destructive/15 px-1 py-0.5 text-[10px] text-destructive">
                      emboldened
                    </span>
                  )}
                  <MoraleStateChip state={g.morale_state} />
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <span className="text-xs text-muted-foreground">
        In the standoff: {summary.participants.join(', ')}.
      </span>
    </div>
  );
}
