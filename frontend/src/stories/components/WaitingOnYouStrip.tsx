/**
 * WaitingOnYouStrip (#4188): the GM Dashboard opens on this, one row per
 * kind of thing waiting on the GM, each a door to the page that answers it.
 *
 * The rows read `GET /api/gm/attention/`, the same payload whose `total`
 * the header's GMing badge shows, so the badge and the strip never disagree
 * (ADR-4188). A non-zero row links to its page and names it; a zero row
 * renders muted and unlinked, so quiet reads as quiet. Drawn after the demo's
 * Screen B3: the count first, then the row's name, then the door.
 */

import { Link } from 'react-router-dom';
import type { GMAttention } from '@/gm/queries';

type AttentionKey = Exclude<keyof GMAttention, 'total'>;

interface StripRow {
  key: AttentionKey;
  label: string;
  /** The page the row opens, named the way its header link names it. */
  door: string;
  to: string;
}

/** Row order is the spec's: offers, invites, requests, claims to approve, my claims, sessions. */
const ROWS: StripRow[] = [
  { key: 'story_offers', label: 'Story offers', door: 'Offers', to: '/stories/my-offers' },
  {
    key: 'crossover_invites',
    label: 'Crossover invites',
    door: 'Crossover Inbox',
    to: '/crossover/inbox',
  },
  {
    key: 'sheet_update_requests',
    label: 'Sheet update requests',
    door: 'Update Requests',
    to: '/gm/update-requests',
  },
  {
    key: 'claims_to_approve',
    label: 'Assistant GM claims to approve',
    door: 'Lead GM Queue',
    to: '/stories/gm-queue',
  },
  { key: 'my_claims', label: 'My claims', door: 'My Claims', to: '/stories/my-claims' },
  {
    key: 'session_requests',
    label: 'Session requests',
    door: 'Lead GM Queue',
    to: '/stories/gm-queue',
  },
];

const ROW_CLASS = 'flex items-center gap-3 px-4 py-2.5 text-sm border-t first:border-t-0';

export function WaitingOnYouStrip({ attention }: { attention: GMAttention }) {
  return (
    <section data-testid="waiting-on-you">
      <h2 className="mb-2 text-lg font-semibold">Waiting on you</h2>
      <ul className="overflow-hidden rounded-lg border">
        {ROWS.map((row) => {
          const count = attention[row.key];
          return count > 0 ? (
            <li key={row.key} className="border-t first:border-t-0">
              <Link
                to={row.to}
                className="flex items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-accent"
                data-testid={`waiting-${row.key}`}
              >
                <span className="min-w-7 font-bold tabular-nums">{count}</span>
                <span>{row.label}</span>
                <span className="ml-auto text-muted-foreground">{row.door} →</span>
              </Link>
            </li>
          ) : (
            <li
              key={row.key}
              className={`${ROW_CLASS} text-muted-foreground`}
              data-testid={`waiting-${row.key}`}
            >
              <span className="min-w-7 font-bold tabular-nums">0</span>
              <span>{row.label}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
