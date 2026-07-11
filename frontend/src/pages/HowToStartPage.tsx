import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function HowToStartPage() {
  return (
    <div className="container mx-auto max-w-3xl space-y-8 px-4 py-12">
      <header className="space-y-2 text-center">
        <h1 className="text-3xl font-bold tracking-tight">How to Start Playing</h1>
        <p className="text-muted-foreground">
          From first click to standing in a scene, in three steps.
        </p>
      </header>

      <ol className="space-y-6">
        <li>
          <Card>
            <CardHeader>
              <CardTitle>1. Register an account</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                Create an account and verify your email. That's the only setup there is — the game
                runs entirely in your browser.
              </p>
              <Button asChild size="sm">
                <Link to="/register">Register</Link>
              </Button>
            </CardContent>
          </Card>
        </li>
        <li>
          <Card>
            <CardHeader>
              <CardTitle>2. Get a character — two ways</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <p className="font-medium">Apply for a roster character</p>
                <p className="text-muted-foreground">
                  Take up an established character with a history, family, and hooks already in
                  play. Browse the{' '}
                  <Link className="text-primary underline" to="/roster">
                    roster
                  </Link>
                  , open a character page, and send an application. Staff review it and you'll get
                  an email either way.
                </p>
              </div>
              <div>
                <p className="font-medium">Create your own</p>
                <p className="text-muted-foreground">
                  Build a new character from origin to final touches in the{' '}
                  <Link className="text-primary underline" to="/characters/create">
                    character creator
                  </Link>
                  . Your application is reviewed the same way, with comments if anything needs a
                  tweak.
                </p>
              </div>
            </CardContent>
          </Card>
        </li>
        <li>
          <Card>
            <CardHeader>
              <CardTitle>3. Enter the game</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                Once approved, log in and press Play. You'll arrive in the world with a guided first
                arc that teaches the game as you play it — no manual required.
              </p>
              <Button asChild size="sm">
                <Link to="/game">Play</Link>
              </Button>
            </CardContent>
          </Card>
        </li>
      </ol>
    </div>
  );
}
