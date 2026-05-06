import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useThreads } from '../queries';

interface ThreadListProps {
  /**
   * Optional filter to show only threads with a specific target_kind.
   * If not provided, all threads are shown.
   */
  targetKind?: string;
}

/**
 * Read-only list of the caller's Thread rows.
 *
 * Displays: name, target_kind badge, level, resonance.
 * Fetches all threads for the requesting account via useThreads().
 * Optionally filters by targetKind if provided.
 */
export function ThreadList({ targetKind }: ThreadListProps) {
  const { data, isLoading } = useThreads();
  const threads = data?.results ?? [];

  if (isLoading) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-center text-sm text-muted-foreground">Loading threads...</p>
        </CardContent>
      </Card>
    );
  }

  const filteredThreads = targetKind
    ? threads.filter((thread) => thread.target_kind === targetKind)
    : threads;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Threads</CardTitle>
      </CardHeader>
      <CardContent>
        {filteredThreads.length > 0 ? (
          <ul className="space-y-3">
            {filteredThreads.map((thread) => (
              <li
                key={thread.id}
                className="flex items-center justify-between gap-4 border-b pb-3 text-sm last:border-b-0 last:pb-0"
              >
                <div className="flex-1 overflow-hidden">
                  <div className="truncate font-medium">{thread.name}</div>
                  <div className="flex items-center gap-2 pt-1">
                    <span className="inline-block rounded bg-muted px-2 py-1 text-xs font-medium">
                      {thread.target_kind}
                    </span>
                    <span className="text-muted-foreground">Level {thread.level / 10}</span>
                  </div>
                </div>
                <div className="shrink-0 text-right text-xs text-muted-foreground">
                  {thread.resonance_name}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-center text-sm text-muted-foreground">No threads.</p>
        )}
      </CardContent>
    </Card>
  );
}
