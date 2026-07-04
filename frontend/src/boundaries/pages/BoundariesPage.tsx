/**
 * BoundariesPage — player content-boundary authoring surface (#1771).
 *
 * "My boundaries" (hard lines + advisories) is account-wide (owner =
 * PlayerData) — no character selection needed. "Treasured subjects" is
 * per-character (owner = RosterTenure), so it reuses the same
 * MyTenureSelect-driven pattern as the consent PrivacyPage.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import MyTenureSelect from '@/components/MyTenureSelect';
import { PlayerBoundaryList } from '../components/PlayerBoundaryList';
import { TreasuredSubjectList } from '../components/TreasuredSubjectList';
import { TreasuredSignoffPrompt } from '../components/TreasuredSignoffPrompt';

function BoundariesPageInner() {
  const [tenureId, setTenureId] = useState<number | null>(null);
  const [beatIdInput, setBeatIdInput] = useState('');
  const beatId = beatIdInput !== '' ? Number(beatIdInput) : null;

  return (
    <div className="mt-4 space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>My content boundaries</CardTitle>
          <CardDescription>
            Hard lines are auto-blocked from stakes across every character you play. Advisories are
            communicated, and can be shared with scene partners.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PlayerBoundaryList />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Treasured subjects</CardTitle>
          <CardDescription>
            Pick a character to manage what they treasure — staking one of these requires your
            pre-scene sign-off.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <MyTenureSelect value={tenureId} onChange={setTenureId} label="Character" />
          {tenureId !== null && <TreasuredSubjectList tenureId={tenureId} />}
        </CardContent>
      </Card>

      {tenureId !== null && (
        <Card>
          <CardHeader>
            <CardTitle>Pre-scene sign-offs</CardTitle>
            <CardDescription>
              A GM staking one of your treasured subjects in a beat will ask you to sign off
              beforehand. Check a specific beat here, or withdraw a sign-off you already granted.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="w-40 space-y-1">
              <Label htmlFor="beat-id-input">Beat #</Label>
              <Input
                id="beat-id-input"
                type="number"
                min={1}
                value={beatIdInput}
                onChange={(e) => setBeatIdInput(e.target.value)}
                placeholder="e.g. 42"
              />
            </div>
            {beatId != null && beatId > 0 && (
              <TreasuredSignoffPrompt beatId={beatId} tenureId={tenureId} />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function BoundariesPage() {
  return (
    <ErrorBoundary>
      <BoundariesPageInner />
    </ErrorBoundary>
  );
}
