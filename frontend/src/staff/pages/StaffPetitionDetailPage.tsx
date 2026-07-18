/**
 * StaffPetitionDetailPage (#2288) — triage one emergency petition: the sender's
 * track record (kudos, actioned/dismissed counts), resolve with notes, and the
 * silent perma-ignore toggle for cried-wolf senders.
 */

import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/evennia_replacements/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import type { SenderContext } from '@/staff/types';
import { staffKeys } from '@/staff/queries';

interface PetitionDetail {
  id: number;
  category: string;
  category_display: string;
  scene: number | null;
  subject_character: number | null;
  description: string;
  status: string;
  staff_notes: string;
  created_at: string;
  resolved_at: string | null;
  sender_context: SenderContext | null;
}

async function fetchPetition(id: number): Promise<PetitionDetail> {
  const res = await apiFetch(`/api/player-submissions/petitions/${id}/`);
  if (!res.ok) throw new Error('Failed to load the petition');
  return res.json();
}

export function StaffPetitionDetailPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { id } = useParams<{ id: string }>();
  const petitionId = id ? parseInt(id, 10) : undefined;
  const [notes, setNotes] = useState('');

  const { data: petition, isLoading } = useQuery({
    queryKey: ['staff-petition', petitionId],
    queryFn: () => fetchPetition(petitionId as number),
    enabled: petitionId != null,
  });

  const resolve = useMutation({
    mutationFn: async (status: 'reviewed' | 'dismissed') => {
      const res = await apiFetch(`/api/player-submissions/petitions/${petitionId}/resolve/`, {
        method: 'POST',
        body: JSON.stringify({ status, staff_notes: notes }),
      });
      if (!res.ok) throw new Error('Failed to resolve the petition');
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: staffKeys.all }).catch(() => {});
      navigate('/staff/inbox');
    },
  });

  const ignore = useMutation({
    mutationFn: async (ignored: boolean) => {
      const res = await apiFetch(`/api/player-submissions/petitions/${petitionId}/ignore-sender/`, {
        method: 'POST',
        body: JSON.stringify({ ignored }),
      });
      if (!res.ok) throw new Error('Failed to update the ignore bit');
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff-petition', petitionId] }).catch(() => {});
      qc.invalidateQueries({ queryKey: staffKeys.all }).catch(() => {});
    },
  });

  if (isLoading) return <p className="p-8 text-muted-foreground">Loading...</p>;
  if (!petition) return <p className="p-8 text-muted-foreground">Petition not found.</p>;

  const ctx = petition.sender_context;

  return (
    <div className="container mx-auto max-w-4xl space-y-6 px-4 py-8">
      <h1 className="text-2xl font-bold">Petition Detail</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>
              Petition #{petition.id} — {petition.category_display}
            </span>
            <Badge>{petition.status}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Description</p>
            <p className="whitespace-pre-wrap">{petition.description}</p>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="font-medium text-muted-foreground">Submitted</p>
              <p>{new Date(petition.created_at).toLocaleString()}</p>
            </div>
            {petition.scene != null && (
              <div>
                <p className="font-medium text-muted-foreground">Scene</p>
                <p>#{petition.scene}</p>
              </div>
            )}
            {petition.subject_character != null && (
              <div>
                <p className="font-medium text-muted-foreground">Subject character</p>
                <p>#{petition.subject_character}</p>
              </div>
            )}
          </div>
          {ctx && (
            <div className="rounded border p-3 text-sm" data-testid="sender-context">
              <p className="font-medium text-muted-foreground">Sender track record</p>
              <p>
                Kudos {ctx.kudos_total} &middot; actioned {ctx.actioned_count} &middot; dismissed{' '}
                {ctx.dismissed_count}
                {ctx.is_ignored && (
                  <span className="ml-2 font-semibold text-destructive">perma-ignored</span>
                )}
              </p>
              <Button
                size="sm"
                variant="outline"
                className="mt-2"
                disabled={ignore.isPending}
                onClick={() => ignore.mutate(!ctx.is_ignored)}
                title="Silent: the sender is never told. Their petitions persist but stop surfacing."
              >
                {ctx.is_ignored ? 'Lift perma-ignore' : 'Perma-ignore this sender'}
              </Button>
            </div>
          )}
          {petition.staff_notes && (
            <div>
              <p className="text-sm font-medium text-muted-foreground">Staff notes</p>
              <p className="whitespace-pre-wrap">{petition.staff_notes}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {petition.status === 'open' && (
        <Card>
          <CardHeader>
            <CardTitle>Resolve</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Staff notes (visible to the sender)"
              rows={3}
            />
            <div className="flex gap-2">
              <Button disabled={resolve.isPending} onClick={() => resolve.mutate('reviewed')}>
                Actioned
              </Button>
              <Button
                variant="outline"
                disabled={resolve.isPending}
                onClick={() => resolve.mutate('dismissed')}
              >
                Dismiss
              </Button>
            </div>
            {(resolve.isError || ignore.isError) && (
              <p className="text-sm text-destructive">Something went wrong. Try again.</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
