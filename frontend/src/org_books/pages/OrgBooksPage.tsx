/**
 * OrgBooksPage — the family books / management screen (#930).
 *
 * One composite read (GET /api/currency/org-books/{orgId}/) renders the whole
 * page: treasury, graft, income streams, debts, obligations, contributions,
 * and the recent ledger. Exact numbers, per the ledger tenet — the books are
 * where a house stops estimating. Line-item affordances (summon a steward or
 * the creditor's representative about a row) arrive with the NPC-summon work;
 * the row IDs in the payload exist for that.
 */

import { useParams } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatCoppers } from '@/lib/currency';
import { formatRelativeTime } from '@/lib/relativeTime';
import type { DebtRow } from '@/org_books/api';
import { useOrgBooks } from '@/org_books/queries';

// ---------------------------------------------------------------------------
// Small display helpers
// ---------------------------------------------------------------------------

/** 50 bps → "0.5%/mo" */
function formatMonthlyInterest(bps: number): string {
  return `${(bps / 100).toLocaleString('en-US', { maximumFractionDigits: 2 })}%/mo`;
}

function DebtStatusBadge({ debt }: { debt: DebtRow }) {
  if (debt.in_default) return <Badge variant="destructive">In default</Badge>;
  if (debt.diverting) return <Badge variant="secondary">Diverting</Badge>;
  return <Badge variant="outline">Current</Badge>;
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function EmptyRows({ label }: { label: string }) {
  return <p className="py-2 text-sm text-muted-foreground">{label}</p>;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function BooksSkeleton() {
  return (
    <div className="space-y-4" data-testid="org-books-skeleton">
      <Skeleton className="h-8 w-64" />
      <div className="grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-40" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary)
// ---------------------------------------------------------------------------

function OrgBooksInner({ orgId }: { orgId: number }) {
  const { data: books, isLoading } = useOrgBooks(orgId);

  if (isLoading || !books) return <BooksSkeleton />;

  return (
    <div className="space-y-4" data-testid="org-books">
      <h1 className="text-2xl font-bold">{books.organization_name} — the Books</h1>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Treasury</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold" data-testid="treasury-balance">
              {formatCoppers(books.balance)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Spending authority
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">Ranks 1–{books.spend_rank_max}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">may draw on the treasury</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-muted-foreground">Graft</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{books.graft_pct}%</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              leaks from every income before it reaches the treasury
            </p>
          </CardContent>
        </Card>
      </div>

      <SectionCard title="Income">
        {books.income_streams.length === 0 ? (
          <EmptyRows label="No income streams on the books." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stream</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead className="text-right">Gross / cycle</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {books.income_streams.map((stream) => (
                <TableRow key={stream.id}>
                  <TableCell className="font-medium">{stream.name}</TableCell>
                  <TableCell className="text-muted-foreground">{stream.kind}</TableCell>
                  <TableCell className="text-right">{formatCoppers(stream.gross_amount)}</TableCell>
                  <TableCell>
                    {stream.active ? (
                      <Badge variant="outline">Active</Badge>
                    ) : (
                      <Badge variant="secondary">Dormant</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      <SectionCard title="Debts">
        {books.debts.length === 0 ? (
          <EmptyRows label="The house owes no one. Enjoy it while it lasts." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Creditor</TableHead>
                <TableHead className="text-right">Principal</TableHead>
                <TableHead className="text-right">Arrears</TableHead>
                <TableHead className="text-right">Interest</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {books.debts.map((debt) => (
                <TableRow key={debt.id}>
                  <TableCell className="font-medium">{debt.creditor}</TableCell>
                  <TableCell className="text-right">{formatCoppers(debt.principal)}</TableCell>
                  <TableCell className="text-right">
                    {debt.arrears > 0 ? (
                      <span className="text-destructive">{formatCoppers(debt.arrears)}</span>
                    ) : (
                      formatCoppers(0)
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatMonthlyInterest(debt.interest_bps_monthly)}
                  </TableCell>
                  <TableCell>
                    <DebtStatusBadge debt={debt} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      <SectionCard title="Obligations">
        {books.obligations.length === 0 ? (
          <EmptyRows label="No standing obligations." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Obligation</TableHead>
                <TableHead>Owed to</TableHead>
                <TableHead className="text-right">Share of declared income</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {books.obligations.map((obligation) => (
                <TableRow key={obligation.id}>
                  <TableCell className="font-medium">{obligation.name}</TableCell>
                  <TableCell>{obligation.to_organization}</TableCell>
                  <TableCell className="text-right">{obligation.percent}%</TableCell>
                  <TableCell>
                    {obligation.active ? (
                      <Badge variant="outline">Active</Badge>
                    ) : (
                      <Badge variant="secondary">Suspended</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      <SectionCard title="Contributions">
        {books.contributions.length === 0 ? (
          <EmptyRows label="No member contributions recorded." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Member</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead className="text-right">When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {books.contributions.map((contribution) => (
                <TableRow key={contribution.id}>
                  <TableCell className="font-medium">{contribution.persona_name}</TableCell>
                  <TableCell className="text-right">{formatCoppers(contribution.amount)}</TableCell>
                  <TableCell className="text-muted-foreground">{contribution.reason}</TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {formatRelativeTime(contribution.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>

      <SectionCard title="Recent ledger">
        {books.ledger.length === 0 ? (
          <EmptyRows label="No movements yet." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-20" />
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead className="text-right">When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {books.ledger.map((entry) => (
                <TableRow key={`${entry.direction}-${entry.id}`}>
                  <TableCell>
                    {entry.direction === 'in' ? (
                      <Badge variant="outline">In</Badge>
                    ) : (
                      <Badge variant="secondary">Out</Badge>
                    )}
                  </TableCell>
                  <TableCell
                    className={`text-right ${entry.direction === 'out' ? 'text-destructive' : ''}`}
                  >
                    {formatCoppers(entry.amount)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{entry.reason}</TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {formatRelativeTime(entry.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </SectionCard>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function OrgBooksPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const id = Number(orgId);

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <ErrorBoundary>
        <OrgBooksInner orgId={Number.isFinite(id) ? id : 0} />
      </ErrorBoundary>
    </div>
  );
}
