import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useMyRosterEntriesQuery } from '@/roster/queries';

type SubmissionFn = (data: {
  reporter_persona: number;
  description: string;
}) => Promise<{ id: number }>;

interface SubmissionFormProps {
  title: string;
  intro: string;
  placeholder: string;
  successMessage: string;
  submitFn: SubmissionFn;
}

/**
 * Generic player-submission form used by both Feedback and Bug Report pages.
 *
 * Auto-selects the user's first character's primary persona as the
 * reporter_persona. If the user has no character with a primary persona,
 * shows an error state directing them to create a character first.
 */
export function SubmissionForm({
  title,
  intro,
  placeholder,
  successMessage,
  submitFn,
}: SubmissionFormProps) {
  const navigate = useNavigate();
  const [description, setDescription] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const { data: characters, isLoading } = useMyRosterEntriesQuery(true);

  const personaId =
    characters?.find((c) => c.primary_persona_id !== null)?.primary_persona_id ?? null;

  const mutation = useMutation({
    mutationFn: submitFn,
    onSuccess: () => setSubmitted(true),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!personaId || !description.trim()) return;
    mutation.mutate({
      reporter_persona: personaId,
      description: description.trim(),
    });
  }

  if (isLoading) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-8">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (personaId === null) {
    return (
      <div className="container mx-auto max-w-2xl px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle>{title}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground">
              You need at least one character before you can submit.
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
            <p>{successMessage}</p>
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
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">{intro}</p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={placeholder}
              rows={8}
              disabled={mutation.isPending}
            />
            {mutation.isError ? (
              <p className="text-sm text-destructive">Submission failed. Please try again later.</p>
            ) : null}
            <div className="flex justify-end">
              <Button type="submit" disabled={mutation.isPending || !description.trim()}>
                {mutation.isPending ? 'Submitting...' : 'Submit'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
