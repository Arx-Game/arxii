import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { HISTORY_PAGE_SIZE } from './api';
import { describeChange } from './changes';
import { useClockHistory } from './queries';

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Who changed the clock, when, how and why, newest first. */
export function RecentChanges() {
  const [page, setPage] = useState(1);
  const { data } = useClockHistory(page);
  if (!data) return null;
  const pages = Math.max(1, Math.ceil(data.count / HISTORY_PAGE_SIZE));

  return (
    <section aria-labelledby="clock-changes" className="space-y-3">
      <h2 id="clock-changes" className="text-lg font-semibold">
        Recent changes
      </h2>
      {data.results.length === 0 ? (
        <p className="text-sm text-muted-foreground">No changes yet.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Who</TableHead>
              <TableHead>What changed</TableHead>
              <TableHead>Reason</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.results.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="whitespace-nowrap tabular-nums">
                  {when(row.changed_at)}
                </TableCell>
                <TableCell>{row.changed_by_name}</TableCell>
                <TableCell>{describeChange(row)}</TableCell>
                <TableCell>{row.reason}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {pages > 1 && (
        <div className="flex items-center gap-3 text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Newer
          </Button>
          <span className="tabular-nums text-muted-foreground">
            {page} of {pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => setPage(page + 1)}
          >
            Older
          </Button>
        </div>
      )}
    </section>
  );
}
