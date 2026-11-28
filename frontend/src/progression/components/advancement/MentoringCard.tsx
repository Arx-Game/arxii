/**
 * MentoringCard (#5326) — where a mentor answers the students who named her.
 *
 * A student who names a mentor only asks her. The training counts once the mentor accepts,
 * and either of them can end it later. This card lists, for the whole ACCOUNT rather than the
 * selected character, every request waiting on an answer ("Asked to teach", with Accept and
 * Decline) and every student the account teaches ("Teaching", with Stop). A game master who
 * holds an NPC mentor sees the NPC's requests here, and each row names which character was
 * asked.
 *
 * Each button posts to the training viewset's `accept-mentoring`, `decline-mentoring` or
 * `stop-mentoring` route. The sentence the server returns is the success toast, and a
 * refusal's sentence is the error toast with the row left in place. Both lists are
 * refetched after every answer. The card renders nothing while the account has no request
 * and no student.
 */

import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { MentoringAnswer } from '@/skills/api';
import { useAnswerMentoringMutation, useMentoringQuery } from '@/skills/queries';
import type { MentoringRow } from '@/skills/types';

export function MentoringCard() {
  const { data } = useMentoringQuery();
  const answer = useAnswerMentoringMutation();

  const requests = data?.requests ?? [];
  const students = data?.students ?? [];
  if (requests.length === 0 && students.length === 0) return null;

  function handleAnswer(row: MentoringRow, kind: MentoringAnswer) {
    answer.mutate(
      { allocationId: row.allocation_id, answer: kind },
      {
        onSuccess: (result) => toast.success(result.detail),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not answer the request.'),
      }
    );
  }

  const busyFor = (row: MentoringRow) =>
    answer.isPending && answer.variables?.allocationId === row.allocation_id;

  return (
    <Card data-testid="mentoring-card">
      <CardHeader>
        <CardTitle className="text-base">Mentoring</CardTitle>
        {requests.length > 0 && <CardDescription>Asked to teach</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-3">
        {requests.map((row) => (
          <div
            key={row.allocation_id}
            className="flex items-center justify-between gap-3 rounded-lg border p-3"
            data-testid="mentoring-request-row"
          >
            <div className="min-w-0 font-medium">
              {row.student_name} asks {row.mentor_name} to teach {row.skill_name}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                size="sm"
                disabled={busyFor(row)}
                onClick={() => handleAnswer(row, 'accept')}
                data-testid={`mentoring-accept-${row.allocation_id}`}
              >
                Accept
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={busyFor(row)}
                onClick={() => handleAnswer(row, 'decline')}
                data-testid={`mentoring-decline-${row.allocation_id}`}
              >
                Decline
              </Button>
            </div>
          </div>
        ))}
        {students.length > 0 && (
          <>
            <h3 className="text-sm font-medium text-muted-foreground">Teaching</h3>
            {students.map((row) => (
              <div
                key={row.allocation_id}
                className="flex items-center justify-between gap-3 rounded-lg border p-3"
                data-testid="mentoring-student-row"
              >
                <div className="min-w-0 font-medium">
                  {row.student_name}: {row.skill_name} (as {row.mentor_name})
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busyFor(row)}
                  onClick={() => handleAnswer(row, 'stop')}
                  data-testid={`mentoring-stop-${row.allocation_id}`}
                >
                  Stop
                </Button>
              </div>
            ))}
          </>
        )}
      </CardContent>
    </Card>
  );
}
