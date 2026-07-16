import { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useAccount } from '@/store/hooks';

interface RequireCharacterProps {
  children: ReactNode;
}

/**
 * Route guard that ensures the user has at least one character.
 *
 * Shows a friendly "create a character first" card instead of mounting the
 * page — which would crash on API 403s from character-scoped endpoints
 * (threads, magic progression, alterations).
 *
 * Use inside ProtectedRoute: RequireCharacter assumes the user is already
 * authenticated.
 */
export function RequireCharacter({ children }: RequireCharacterProps) {
  const account = useAccount();
  const hasCharacters = (account?.available_characters?.length ?? 0) > 0;

  if (hasCharacters) {
    return <>{children}</>;
  }

  return (
    <div className="container mx-auto py-8">
      <Card>
        <CardHeader>
          <CardTitle>You need a character first</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            This page requires an active character. Browse the roster to find a character to play,
            or start a new character application.
          </p>
          <div className="flex gap-2">
            <Button asChild>
              <Link to="/roster">Browse the roster</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
