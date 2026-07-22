/**
 * GMUpdateRequestsPage (#2631) — a GM's queue of sheet-update requests on
 * their tables. Side-by-side current/proposed text for prose kinds; approve
 * or reject with notes. The GM's job is a yes/no story-fit judgment — the
 * page offers no way to edit the player's text, by design (ADR-0155).
 */

import { useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

import { useSignoffMutation, useUpdateRequestsQuery } from '../queries';
import { REQUEST_KINDS, REQUEST_STATUSES, type TableUpdateRequest } from '../types';

const STATUS_OPTIONS: { label: string; value: string | undefined }[] = [
  { label: 'Pending', value: REQUEST_STATUSES.PENDING },
  { label: 'Approved', value: REQUEST_STATUSES.APPROVED },
  { label: 'Completed', value: REQUEST_STATUSES.COMPLETED },
  { label: 'Rejected', value: REQUEST_STATUSES.REJECTED },
  { label: 'All', value: undefined },
];

function RequestCard({ request }: { request: TableUpdateRequest }) {
  const signoff = useSignoffMutation();
  const [notes, setNotes] = useState('');

  const prose = request.profile_text_details;
  const distinction = request.distinction_details;
  const isPending = request.status === REQUEST_STATUSES.PENDING;

  return (
    <Card data-testid="gm-request-card">
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2 text-base">
          <span>
            {request.persona_name} · {request.table_name} ·{' '}
            {request.kind === REQUEST_KINDS.PROFILE_TEXT
              ? `Profile: ${prose?.field ?? ''}`
              : `Distinction: ${
                  distinction?.distinction_name ?? distinction?.held_distinction_name ?? ''
                } (${distinction?.action ?? ''}${
                  distinction?.action === 'add' ? ` → rank ${distinction?.rank}` : ''
                })`}
          </span>
          <Badge variant="outline">{request.status}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm italic text-muted-foreground">Reason: {request.player_reasoning}</p>

        {request.kind === REQUEST_KINDS.PROFILE_TEXT && prose && (
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h4 className="mb-1 text-sm font-semibold text-muted-foreground">Current</h4>
              <p className="whitespace-pre-wrap rounded-md border p-3 text-sm">
                {prose.current_text || '(empty)'}
              </p>
            </div>
            <div>
              <h4 className="mb-1 text-sm font-semibold text-muted-foreground">Proposed</h4>
              <p className="whitespace-pre-wrap rounded-md border p-3 text-sm">
                {prose.proposed_text}
              </p>
            </div>
          </div>
        )}

        {request.gm_notes && (
          <p className="text-sm">
            <span className="font-medium">Notes:</span> {request.gm_notes}
          </p>
        )}

        {isPending && (
          <div className="space-y-2">
            <Textarea
              rows={2}
              placeholder="Notes to the player (optional for approval, kind for rejection)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={signoff.isPending}
                onClick={() => signoff.mutate({ id: request.id, body: { approve: true, notes } })}
              >
                Approve
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={signoff.isPending}
                onClick={() => signoff.mutate({ id: request.id, body: { approve: false, notes } })}
              >
                Reject
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function GMUpdateRequestsPage() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>(REQUEST_STATUSES.PENDING);
  const { data, isLoading } = useUpdateRequestsQuery({ role: 'gm', status: statusFilter });
  const requests = data?.results ?? [];

  return (
    <div className="container mx-auto max-w-5xl px-4 py-8">
      <h1 className="mb-2 text-2xl font-bold">Sheet Update Requests</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Players at your tables proposing sheet changes. Your call is story-fit, yes or no — the
        player wrote the content, and prose approvals apply immediately.
      </p>

      <div className="mb-6 flex flex-wrap gap-2">
        {STATUS_OPTIONS.map((option) => (
          <Button
            key={option.label}
            variant={statusFilter === option.value ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : requests.length === 0 ? (
        <p className="py-8 text-center text-muted-foreground">No requests here.</p>
      ) : (
        <div className="space-y-4">
          {requests.map((request) => (
            <RequestCard key={request.id} request={request} />
          ))}
        </div>
      )}
    </div>
  );
}
