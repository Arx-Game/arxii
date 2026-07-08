import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { createPlayerReport } from '@/submissions/playerReportApi';

const CATEGORIES = [
  { value: 'harassment', label: 'Harassment' },
  { value: 'ooc_abuse', label: 'OOC Abuse' },
  { value: 'red_flag', label: 'FYI / Red Flag' },
  { value: 'other', label: 'Other' },
] as const;

/**
 * Player-facing harassment report form (#1279).
 *
 * Captures: who you're reporting (reported persona — by name search), what happened,
 * the category, and what you already did about it. The backend auto-derives the
 * reported account from the persona's current tenure — staff see the real identity
 * behind the mask immediately. The reporter learns nothing about the offender's
 * real identity or alts from filing.
 */
export function PlayerReportPage() {
  const navigate = useNavigate();
  const { data: characters, isLoading } = useMyRosterEntriesQuery(true);

  const reporterPersonaId = useMemo(
    () => characters?.find((c) => c.primary_persona_id !== null)?.primary_persona_id ?? null,
    [characters]
  );

  const [reportedPersonaName, setReportedPersonaName] = useState('');
  const [category, setCategory] = useState<string>('harassment');
  const [description, setDescription] = useState('');
  const [askedToStop, setAskedToStop] = useState(false);
  const [blockedOrMuted, setBlockedOrMuted] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const mutation = useMutation({
    mutationFn: createPlayerReport,
    onSuccess: () => setSubmitted(true),
    onError: (e: Error) => setError(e.message),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!reporterPersonaId || !description.trim() || !reportedPersonaName.trim()) return;
    setError('');
    mutation.mutate({
      reporter_persona: reporterPersonaId,
      reported_persona_name: reportedPersonaName.trim(),
      category,
      behavior_description: description.trim(),
      asked_to_stop: askedToStop,
      blocked_or_muted: blockedOrMuted,
    });
  }

  if (isLoading) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-8">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (reporterPersonaId === null) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle>Report a Player</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">
              You need at least one character before you can submit a report.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle>Thank you</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p>
              Your report has been submitted. Staff will review it — they can see the real identity
              behind the persona. You won't receive any information about the reported player's
              identity or alts.
            </p>
            <Button onClick={() => navigate('/')}>Return home</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-2xl px-4 py-8">
      <Card>
        <CardHeader>
          <CardTitle>Report a Player</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Report problematic behavior from another player. Staff see the real identity behind the
            persona — anonymity does not shield abuse. You won't learn anything about the reported
            player's identity or alts from filing.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="reported-persona">Who are you reporting?</Label>
              <input
                id="reported-persona"
                type="text"
                value={reportedPersonaName}
                onChange={(e) => setReportedPersonaName(e.target.value)}
                placeholder="Character or persona name"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                required
                disabled={mutation.isPending}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="category">Category</Label>
              <Select value={category} onValueChange={setCategory} disabled={mutation.isPending}>
                <SelectTrigger id="category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">What happened?</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe the behavior you're reporting..."
                rows={8}
                required
                disabled={mutation.isPending}
              />
            </div>

            <div className="space-y-3">
              <Label>What have you already done?</Label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={askedToStop}
                  onChange={(e) => setAskedToStop(e.target.checked)}
                  disabled={mutation.isPending}
                  className="h-4 w-4 rounded border-input"
                />
                I asked them to stop
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={blockedOrMuted}
                  onChange={(e) => setBlockedOrMuted(e.target.checked)}
                  disabled={mutation.isPending}
                  className="h-4 w-4 rounded border-input"
                />
                I blocked or muted them
              </label>
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}

            <div className="flex justify-end">
              <Button
                type="submit"
                disabled={mutation.isPending || !description.trim() || !reportedPersonaName.trim()}
              >
                {mutation.isPending ? 'Submitting...' : 'Submit Report'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
