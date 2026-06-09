import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import type { PowerLedger, PowerLedgerEntry } from '../types';

const STAGE_LABELS: Record<string, string> = {
  base: 'Channeled intensity',
  flat_modifier: 'Power modifier',
  multiplier: 'Power multiplier',
  term: 'Power term',
  environment: 'Environment',
  reactive: 'Pre-cast reactive edit',
  combat_pull: 'Combat pull',
  penetration: 'Penetration vs resistance',
  clamp: 'Floor / cap',
};
const DRAMATIC = new Set(['penetration', 'environment']);

function formatAmount(entry: PowerLedgerEntry): string {
  if (entry.op === 'multiply') return `${entry.amount > 0 ? '+' : ''}${entry.amount}%`;
  if (entry.op === 'set') return `=${entry.amount}`;
  return `${entry.amount > 0 ? '+' : ''}${entry.amount}`;
}

export function PowerLedgerPanel({ ledger }: { ledger: PowerLedger | null | undefined }) {
  if (!ledger || ledger.entries.length === 0) return null;
  return (
    <Card data-testid="power-ledger-panel" className="mt-2">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Power ledger</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-xs">
        <ul className="space-y-1">
          {ledger.entries.map((entry, i) => (
            <li
              key={i}
              data-testid={`power-ledger-row-${entry.stage}`}
              className={cn(
                'flex items-baseline justify-between gap-2',
                DRAMATIC.has(entry.stage) && 'font-medium text-amber-400'
              )}
            >
              <span>
                <span className="font-medium">{STAGE_LABELS[entry.stage] ?? entry.stage}</span>{' '}
                <span className="text-muted-foreground">{entry.source_label}</span>
              </span>
              <span className="font-mono">
                {formatAmount(entry)}{' '}
                <span className="text-muted-foreground">→ {entry.running_total}</span>
              </span>
            </li>
          ))}
        </ul>
        <Separator className="my-1" />
        <div className="flex items-baseline justify-between font-semibold">
          <span>Total power</span>
          <span className="font-mono" data-testid="power-ledger-total">
            {ledger.total}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
