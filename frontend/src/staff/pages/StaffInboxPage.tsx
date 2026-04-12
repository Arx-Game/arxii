import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useStaffInbox } from '@/staff/queries';
import { useAppSelector } from '@/store/hooks';
import type { SubmissionCategory } from '@/staff/types';
import { detailPath } from '@/staff/utils';

const CATEGORY_OPTIONS: { label: string; value: SubmissionCategory; color: string }[] = [
  {
    label: 'Feedback',
    value: 'player_feedback',
    color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  },
  {
    label: 'Bug Reports',
    value: 'bug_report',
    color: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  },
  {
    label: 'Player Reports',
    value: 'player_report',
    color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  },
  {
    label: 'Applications',
    value: 'character_application',
    color: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200',
  },
];

const STORAGE_KEY = 'staff-inbox-muted-categories';

function loadMutedCategories(): Set<SubmissionCategory> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return new Set(JSON.parse(stored));
  } catch {
    // ignore
  }
  return new Set();
}

function saveMutedCategories(muted: Set<SubmissionCategory>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...muted]));
}

function categoryLabel(sourceType: string): string {
  return CATEGORY_OPTIONS.find((c) => c.value === sourceType)?.label ?? sourceType;
}

function categoryColor(sourceType: string): string {
  return CATEGORY_OPTIONS.find((c) => c.value === sourceType)?.color ?? '';
}

function timeAgo(dateString: string): string {
  const now = new Date();
  const date = new Date(dateString);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function StaffInboxPage() {
  const account = useAppSelector((state) => state.auth.account);
  const [mutedCategories, setMutedCategories] =
    useState<Set<SubmissionCategory>>(loadMutedCategories);
  const [page, setPage] = useState(1);

  const activeCategories = CATEGORY_OPTIONS.map((c) => c.value).filter(
    (c) => !mutedCategories.has(c)
  );

  const { data, isLoading } = useStaffInbox(
    activeCategories.length < CATEGORY_OPTIONS.length ? activeCategories : undefined,
    page
  );

  if (!account?.is_staff) return <Navigate to="/" replace />;

  function toggleCategory(category: SubmissionCategory) {
    setMutedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      saveMutedCategories(next);
      return next;
    });
    setPage(1);
  }

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Staff Inbox</h1>

      {/* Category toggles */}
      <div className="mb-6 flex flex-wrap gap-2">
        {CATEGORY_OPTIONS.map((opt) => (
          <Button
            key={opt.value}
            variant={mutedCategories.has(opt.value) ? 'outline' : 'default'}
            size="sm"
            onClick={() => toggleCategory(opt.value)}
          >
            {opt.label}
          </Button>
        ))}
      </div>

      {/* Items list */}
      {isLoading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : !data?.results.length ? (
        <p className="text-muted-foreground">No open items.</p>
      ) : (
        <>
          <div className="space-y-3">
            {data.results.map((item) => (
              <Link key={`${item.source_type}-${item.source_pk}`} to={detailPath(item)}>
                <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                  <CardContent className="flex items-center justify-between py-4">
                    <div className="flex items-center gap-3">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${categoryColor(item.source_type)}`}
                      >
                        {categoryLabel(item.source_type)}
                      </span>
                      <div>
                        <p className="font-medium">{item.title}</p>
                        <p className="text-sm text-muted-foreground">
                          {item.reporter_summary} &middot; {timeAgo(item.created_at)}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>

          {/* Pagination */}
          {data.num_pages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-4">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {data.current_page} of {data.num_pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= data.num_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
