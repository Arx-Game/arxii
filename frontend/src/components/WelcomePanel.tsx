import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDraft } from '@/character-creation/queries';
import { useAccount } from '@/store/hooks';

export function WelcomePanel() {
  const account = useAccount();
  const hasCharacters = (account?.available_characters?.length ?? 0) > 0;
  const pending = account?.pending_applications ?? [];

  const { data: draft } = useDraft(!!account && !hasCharacters);
  const showDraftLink = !hasCharacters && !!draft;

  if (!account) return null;

  return (
    <section className="container mx-auto py-8">
      <Card>
        <CardHeader>
          <CardTitle>Welcome back, {account.display_name || account.username}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {hasCharacters && (
            <Button asChild>
              <Link to="/game">Enter the game</Link>
            </Button>
          )}
          {pending.length > 0 && (
            <div className="space-y-1">
              <p className="font-medium">Your applications</p>
              {pending.map((app) => (
                <p key={app.id} className="text-muted-foreground">
                  {app.character_name} — pending since{' '}
                  {new Date(app.applied_date).toLocaleDateString()}
                </p>
              ))}
            </div>
          )}
          {showDraftLink && (
            <p>
              <Link to="/characters/create/application" className="text-primary underline">
                Your character application
              </Link>{' '}
              — check its status.
            </p>
          )}
          {!hasCharacters && pending.length === 0 && (
            <div className="space-y-3">
              <p>You don't have a character yet — two ways to get one:</p>
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="secondary">
                  <Link to="/roster">Browse the roster</Link>
                </Button>
                <Button asChild variant="secondary">
                  <Link to="/characters/create">Create a character</Link>
                </Button>
              </div>
              <p className="text-muted-foreground">
                Not sure which?{' '}
                <Link className="text-primary underline" to="/how-to-start">
                  How to start
                </Link>
                .
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
