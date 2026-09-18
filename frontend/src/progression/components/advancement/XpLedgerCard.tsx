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
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): a glance list under the section's
 * own heading, since the sheet's Growth page already says what this is.
 */

import { useCharacterXpLedgerQuery } from '@/progression/queries';
import { Glance, Ledger, Stack, Subheading } from '@/character_sheets/components/sheet/primitives';
import type { GlanceRow } from '@/character_sheets/components/sheet/primitives';

export function XpLedgerCard({ sheetId }: { sheetId: number }) {
  const { data, isLoading, error } = useCharacterXpLedgerQuery(sheetId);

  const rows: GlanceRow[] = data
    ? [
        { label: 'Earned on', value: `${data.earned.toLocaleString()} XP` },
        { label: 'Spent on', value: `${data.spent.toLocaleString()} XP` },
        {
          label: 'Locked from creation',
          value: data.locked > 0 ? `${data.locked.toLocaleString()} XP` : null,
        },
      ]
    : [];

  return (
    <div className="refsheet-stack" data-testid="xp-ledger-card">
      <Subheading>Invested in this character</Subheading>
      {isLoading && <Ledger>Reading the ledger…</Ledger>}
      {error && (
        <p className="refsheet-ledger" style={{ color: 'hsl(var(--destructive))' }}>
          The XP ledger could not be read.
        </p>
      )}
      {data && (
        <Stack>
          <Glance rows={rows} />
          <p className="refsheet-note">
            XP is held by the account, not by any one character. This is the record of where it came
            from and where it went.
          </p>
        </Stack>
      )}
    </div>
  );
}
