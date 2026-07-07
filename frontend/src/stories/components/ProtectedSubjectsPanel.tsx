/**
 * ProtectedSubjectsPanel — GM-authored custody protection list for the
 * selected story, mounted as a tab on StoryAuthorPage (#2001 Task 8).
 *
 * StoryAuthorPage is already owner/lead-GM-gated (the story only appears in
 * the sidebar if the requester owns/leads it, or is staff — see
 * StoryAuthorPage.tsx's comment on GMNotesPanel's identical posture), so this
 * panel doesn't re-implement auth: it just renders the list + add/deactivate/
 * reactivate actions and trusts `IsProtectedSubjectStoryOwnerOrStaff` +
 * `StoryProtectedSubjectViewSet.get_queryset` server-side (404-not-filtered,
 * mirroring world.boundaries's privacy posture).
 */

import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatRelativeTime } from '@/lib/relativeTime';
import {
  useDeactivateProtectedSubject,
  useProtectedSubjects,
  useUpdateProtectedSubject,
} from '../queries';
import type { ProtectedSubject } from '../types';
import { ProtectedSubjectFormDialog } from './ProtectedSubjectFormDialog';
import { SUBJECT_KIND_LABELS } from './SubjectRefFields';

interface ProtectedSubjectsPanelProps {
  storyId: number;
}

function subjectRefDisplay(subject: ProtectedSubject): string {
  if (subject.subject_sheet != null) return `Character sheet #${subject.subject_sheet}`;
  if (subject.subject_item != null) return `Item #${subject.subject_item}`;
  if (subject.subject_society != null) return `Society #${subject.subject_society}`;
  if (subject.subject_organization != null) return `Organization #${subject.subject_organization}`;
  return subject.subject_label || '(unlabeled)';
}

function ProtectedSubjectRow({ subject }: { subject: ProtectedSubject }) {
  const deactivateMutation = useDeactivateProtectedSubject();
  const updateMutation = useUpdateProtectedSubject();

  function handleDeactivate() {
    deactivateMutation.mutate(subject.id, {
      onSuccess: () => toast.success('Protected subject deactivated'),
      onError: () => toast.error('Failed to deactivate protected subject'),
    });
  }

  function handleReactivate() {
    updateMutation.mutate(
      { id: subject.id, body: { is_active: true } },
      {
        onSuccess: () => toast.success('Protected subject reactivated'),
        onError: () => toast.error('Failed to reactivate protected subject'),
      }
    );
  }

  const isActive = subject.is_active ?? true;

  return (
    <li
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-card p-3"
      data-testid="protected-subject-row"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{subjectRefDisplay(subject)}</span>
          <Badge variant="outline">{SUBJECT_KIND_LABELS[subject.subject_kind]}</Badge>
          {!isActive && (
            <Badge className="border-transparent bg-gray-500 text-white">Deactivated</Badge>
          )}
        </div>
        {subject.notes && <p className="mt-1 text-xs text-muted-foreground">{subject.notes}</p>}
        <p className="mt-1 text-xs text-muted-foreground">
          Added {formatRelativeTime(subject.created_at)}
        </p>
      </div>
      <div>
        {isActive ? (
          <Button
            variant="outline"
            size="sm"
            onClick={handleDeactivate}
            disabled={deactivateMutation.isPending}
            data-testid="deactivate-protected-subject-btn"
          >
            {deactivateMutation.isPending ? 'Deactivating…' : 'Deactivate'}
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={handleReactivate}
            disabled={updateMutation.isPending}
            data-testid="reactivate-protected-subject-btn"
          >
            {updateMutation.isPending ? 'Reactivating…' : 'Reactivate'}
          </Button>
        )}
      </div>
    </li>
  );
}

export function ProtectedSubjectsPanel({ storyId }: ProtectedSubjectsPanelProps) {
  const { data, isLoading } = useProtectedSubjects({ story: storyId, page_size: 100 });
  const subjects = data?.results ?? [];

  return (
    <div className="space-y-4" data-testid="protected-subjects-panel">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Story assets flagged as load-bearing. Other GMs must request custody clearance before
          acting against them.
        </p>
        <ProtectedSubjectFormDialog storyId={storyId} />
      </div>

      {isLoading ? (
        <div className="space-y-2" data-testid="protected-subjects-loading">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : subjects.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="protected-subjects-empty">
          No protected subjects yet.
        </p>
      ) : (
        <ul className="space-y-2" data-testid="protected-subjects-list">
          {subjects.map((subject) => (
            <ProtectedSubjectRow key={subject.id} subject={subject} />
          ))}
        </ul>
      )}
    </div>
  );
}
