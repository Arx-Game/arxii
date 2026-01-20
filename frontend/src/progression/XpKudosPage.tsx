/**
 * XP/Kudos page showing account progression data.
 */

import { useAccountProgressionQuery } from './queries';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import type { XPTransaction, KudosTransaction } from './types';

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function XPTransactionRow({ transaction }: { transaction: XPTransaction }) {
  const isPositive = transaction.amount > 0;
  return (
    <div className="flex items-center justify-between border-b py-2 last:border-b-0">
      <div className="flex-1">
        <div className="font-medium">{transaction.reason_display}</div>
        <div className="text-sm text-muted-foreground">
          {transaction.description}
          {transaction.character_name && (
            <span className="ml-1">({transaction.character_name})</span>
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          {formatDate(transaction.transaction_date)}
        </div>
      </div>
      <div className={`text-lg font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
        {isPositive ? '+' : ''}
        {transaction.amount}
      </div>
    </div>
  );
}

function KudosTransactionRow({ transaction }: { transaction: KudosTransaction }) {
  const isPositive = transaction.amount > 0;
  const categoryName =
    transaction.source_category_name || transaction.claim_category_name || 'Unknown';
  return (
    <div className="flex items-center justify-between border-b py-2 last:border-b-0">
      <div className="flex-1">
        <div className="font-medium">{categoryName}</div>
        <div className="text-sm text-muted-foreground">{transaction.description}</div>
        {transaction.awarded_by_name && (
          <div className="text-xs text-muted-foreground">From: {transaction.awarded_by_name}</div>
        )}
        <div className="text-xs text-muted-foreground">
          {formatDate(transaction.transaction_date)}
        </div>
      </div>
      <div className={`text-lg font-bold ${isPositive ? 'text-green-600' : 'text-amber-600'}`}>
        {isPositive ? '+' : ''}
        {transaction.amount}
      </div>
    </div>
  );
}

function BalanceCard({
  title,
  available,
  earned,
  spent,
  spentLabel = 'Spent',
}: {
  title: string;
  available: number;
  earned: number;
  spent: number;
  spentLabel?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-4xl font-bold">{available}</div>
        <CardDescription>Available</CardDescription>
        <div className="mt-2 flex gap-4 text-sm text-muted-foreground">
          <div>Earned: {earned}</div>
          <div>
            {spentLabel}: {spent}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

export function XpKudosPage() {
  const { data, isLoading, error } = useAccountProgressionQuery();

  if (isLoading) {
    return (
      <div className="container mx-auto py-6">
        <h1 className="mb-6 text-2xl font-bold">XP / Kudos</h1>
        <LoadingSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto py-6">
        <h1 className="mb-6 text-2xl font-bold">XP / Kudos</h1>
        <Card>
          <CardContent className="py-8">
            <div className="text-center text-destructive">
              Failed to load progression data. Please try again later.
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const xp = data?.xp;
  const kudos = data?.kudos;
  const xpTransactions = data?.xp_transactions || [];
  const kudosTransactions = data?.kudos_transactions || [];

  return (
    <div className="container mx-auto py-6">
      <h1 className="mb-6 text-2xl font-bold">XP / Kudos</h1>

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <BalanceCard
          title="Experience Points"
          available={xp?.current_available || 0}
          earned={xp?.total_earned || 0}
          spent={xp?.total_spent || 0}
        />
        <BalanceCard
          title="Kudos"
          available={kudos?.current_available || 0}
          earned={kudos?.total_earned || 0}
          spent={kudos?.total_claimed || 0}
          spentLabel="Claimed"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Transaction History</CardTitle>
          <CardDescription>Your recent XP and Kudos activity</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="kudos">
            <TabsList className="mb-4">
              <TabsTrigger value="kudos">Kudos ({kudosTransactions.length})</TabsTrigger>
              <TabsTrigger value="xp">XP ({xpTransactions.length})</TabsTrigger>
            </TabsList>
            <TabsContent value="kudos">
              {kudosTransactions.length > 0 ? (
                <div className="max-h-96 overflow-y-auto">
                  {kudosTransactions.map((t) => (
                    <KudosTransactionRow key={t.id} transaction={t} />
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center text-muted-foreground">
                  No kudos transactions yet
                </div>
              )}
            </TabsContent>
            <TabsContent value="xp">
              {xpTransactions.length > 0 ? (
                <div className="max-h-96 overflow-y-auto">
                  {xpTransactions.map((t) => (
                    <XPTransactionRow key={t.id} transaction={t} />
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center text-muted-foreground">No XP transactions yet</div>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
