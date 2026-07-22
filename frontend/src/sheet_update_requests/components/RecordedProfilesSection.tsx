/**
 * RecordedProfilesSection (#2632) — the owner's Archive profile sittings.
 *
 * Shows COMMISSIONED sittings with the write-up form (completing sets the
 * character's description and archives the text forever) and the permanent
 * recorded archive. Owner-scoped endpoint; rendered only on own sheets.
 */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';

interface RecordedProfile {
  id: number;
  persona: number;
  persona_name: string;
  status: 'commissioned' | 'recorded';
  text: string;
  recorded_by_label: string;
  price_paid: number;
  created_at: string;
  recorded_at: string | null;
  ic_date: string | null;
  era_season_number: number | null;
}

interface Paginated<T> {
  results: T[];
}

const BASE = '/api/npc-services/recorded-profiles/';

async function fetchRecordedProfiles(): Promise<RecordedProfile[]> {
  const res = await apiFetch(BASE);
  if (!res.ok) await throwApiError(res, 'Failed to load recorded profiles');
  const data = (await res.json()) as Paginated<RecordedProfile>;
  return data.results;
}

async function completeRecordedProfile(id: number, text: string): Promise<RecordedProfile> {
  const res = await apiFetch(`${BASE}${id}/complete/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to record the profile');
  return res.json() as Promise<RecordedProfile>;
}

function CommissionedCard({ profile }: { profile: RecordedProfile }) {
  const [text, setText] = useState('');
  const queryClient = useQueryClient();
  const complete = useMutation({
    mutationFn: () => completeRecordedProfile(profile.id, text),
    onSuccess: () => {
      toast.success('Profile recorded — it is now your description.');
      void queryClient.invalidateQueries({ queryKey: ['recorded-profiles'] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Sitting with {profile.recorded_by_label} ({profile.persona_name})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-sm text-muted-foreground">
          Write the profile as the scholar would deliver it — it becomes your description and is
          kept in the Archive forever.
        </p>
        <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} />
        <Button
          size="sm"
          disabled={complete.isPending || !text.trim()}
          onClick={() => complete.mutate()}
        >
          Deliver the profile
        </Button>
      </CardContent>
    </Card>
  );
}

export function RecordedProfilesSection() {
  const { data: profiles } = useQuery({
    queryKey: ['recorded-profiles'],
    queryFn: fetchRecordedProfiles,
  });

  if (!profiles || profiles.length === 0) return null;

  const commissioned = profiles.filter((profile) => profile.status === 'commissioned');
  const recorded = profiles.filter((profile) => profile.status === 'recorded');

  return (
    <section className="space-y-4">
      <h3 className="text-xl font-semibold">Archive profiles</h3>
      {commissioned.map((profile) => (
        <CommissionedCard key={profile.id} profile={profile} />
      ))}
      {recorded.map((profile) => (
        <Card key={profile.id}>
          <CardContent className="space-y-2 py-4">
            <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
              <span>
                {profile.recorded_by_label}
                {profile.era_season_number != null && ` · Season ${profile.era_season_number}`}
                {profile.ic_date && ` · ${new Date(profile.ic_date).toLocaleDateString()}`}
              </span>
              <Badge variant="secondary">recorded</Badge>
            </div>
            <p className="whitespace-pre-wrap text-sm">{profile.text}</p>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}
