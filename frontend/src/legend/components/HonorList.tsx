/**
 * HonorList (#3466 Task 10) — the honors a deed has received, and what people wrote
 * about it. Each honor is a paid, public testimony (`LegendHonor`): a persona's face,
 * how much legend it actually added (after the event ceiling clamped it), how many
 * Golden Hares it cost, and the journal entry the honorer wrote.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

import type { LegendHonor } from '../api';

interface Props {
  honors: LegendHonor[];
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

export function HonorList({ honors }: Props) {
  if (honors.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground" data-testid="honor-list-empty">
        No one has honored this deed yet.
      </p>
    );
  }

  return (
    <ul className="space-y-3" data-testid="honor-list">
      {honors.map((honor) => (
        <li key={honor.id}>
          <Card data-testid="honor-row">
            <CardContent className="space-y-2 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{honor.honorer.name}</span>
                  {honor.established_deed && (
                    <Badge variant="secondary" className="text-xs">
                      Established this deed
                    </Badge>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {formatDate(honor.created_at)}
                </span>
              </div>
              <p className="text-sm font-medium">{honor.journal.title}</p>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                {honor.journal.body}
              </p>
              <div className="flex gap-4 text-xs text-muted-foreground">
                <span>
                  {honor.hares_spent} {honor.hares_spent === 1 ? 'Hare' : 'Hares'} spent
                </span>
                <span>+{honor.value_added} legend</span>
              </div>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
