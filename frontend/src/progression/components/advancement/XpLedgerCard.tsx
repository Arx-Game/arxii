/**
 * XpLedgerCard (#3748) — what this character has earned and what has gone into them.
 *
 * XP is held and spent by the account, so this is not a balance and there is
 * nothing to spend here; it is the record of which character the play behind
 * each award happened on, and which character each purchase was for. The spent
 * figure is what the death-kudos cap is sized on (ADR-0131) and what any future
 * character-loss reimbursement will read.
 *
 * Owner-only, like the endpoint behind it. Unlike the rest of the Advancement
 * tab it does not need the character to be the active puppet: it reads by sheet
 * id and writes nothing.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCharacterXpLedgerQuery } from '@/progression/queries';

function LedgerRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="font-medium tabular-nums">{value.toLocaleString()} XP</span>
    </div>
  );
}

export function XpLedgerCard({ sheetId }: { sheetId: number }) {
  const { data, isLoading, error } = useCharacterXpLedgerQuery(sheetId);

  return (
    <Card data-testid="xp-ledger-card">
      <CardHeader>
        <CardTitle className="text-base">Invested in this character</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">Failed to load the XP ledger.</p>}
        {data && (
          <>
            <LedgerRow label="Earned on" value={data.earned} />
            <LedgerRow label="Spent on" value={data.spent} />
            {data.locked > 0 && <LedgerRow label="Locked from creation" value={data.locked} />}
            <p className="pt-1 text-xs text-muted-foreground">
              Your XP balance is held by your account, not by any one character. These are records
              of where it came from and where it went.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
