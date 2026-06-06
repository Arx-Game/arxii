import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { PrestigeBreakdown } from '../types';

interface Props {
  prestige: PrestigeBreakdown;
}

const SOURCE_ROWS: Array<{ key: keyof PrestigeBreakdown; label: string; hint: string }> = [
  { key: 'dwellings', label: 'Dwellings', hint: 'Polished buildings + tenanted rooms.' },
  { key: 'items', label: 'Fashion', hint: 'Polish on equipped items.' },
  { key: 'orgs', label: 'Organizations', hint: 'Rank-weighted standing in each.' },
  { key: 'deeds', label: 'Deeds', hint: 'Permanent accumulation from Renown events.' },
];

/**
 * Four-axis prestige breakdown plus the total. Negative values can
 * appear after scandals or item loss; the colour mutes on negative.
 */
export function PrestigeBreakdownCard({ prestige }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Prestige</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-3xl font-semibold">{prestige.total.toLocaleString()}</div>
        <ul className="space-y-2 text-sm">
          {SOURCE_ROWS.map((row) => (
            <li key={row.key} className="flex items-baseline justify-between">
              <div>
                <div className="font-medium">{row.label}</div>
                <div className="text-xs text-muted-foreground">{row.hint}</div>
              </div>
              <div
                className={
                  prestige[row.key] < 0 ? 'font-mono text-destructive' : 'font-mono text-foreground'
                }
              >
                {prestige[row.key].toLocaleString()}
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
