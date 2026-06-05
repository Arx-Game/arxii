import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { DeedEntry } from '../types';

interface Props {
  deeds: DeedEntry[];
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

/**
 * Recent deeds — the last N LegendEntry rows, newest first. Phase G API
 * caps the list (default 20). Each row shows title, date, and base
 * legend value; spread totals and societies_aware are surfaced when the
 * deed-detail view lands as a follow-up.
 */
export function DeedsLogCard({ deeds }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Deeds</CardTitle>
      </CardHeader>
      <CardContent>
        {deeds.length === 0 ? (
          <p className="text-sm text-muted-foreground">No deeds recorded yet.</p>
        ) : (
          <ul className="space-y-3 text-sm">
            {deeds.map((deed) => (
              <li key={deed.id} className="border-b pb-2 last:border-b-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{deed.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatDate(deed.created_at)}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  Base legend: <span className="font-mono">{deed.base_value}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
