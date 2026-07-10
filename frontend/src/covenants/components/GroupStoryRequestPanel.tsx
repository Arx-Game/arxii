/**
 * GroupStoryRequestPanel — the covenant-scoped "post an open ask for a GM"
 * control (#2119).
 *
 * Shows the covenant's current open (PENDING) GroupStoryRequest, if any, with
 * a Withdraw control for members who hold can_request_gm. When there is no
 * open request, shows a "Request a GM" form (message textarea + submit)
 * gated on the viewer's can_request_gm capability.
 *
 * Mutation goes exclusively through the generic action-dispatch endpoint
 * (RequestGMForCovenantAction / WithdrawGroupStoryRequestAction) — the same
 * seam telnet's `covenant request-gm` / `covenant withdraw-gm-request` use.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import {
  useCovenantGroupStoryRequest,
  useRequestGMForCovenant,
  useWithdrawGroupStoryRequest,
} from '@/covenants/queries';
import type { ViewerCapabilities } from '@/covenants/api';

export interface GroupStoryRequestPanelProps {
  covenantId: number;
  viewerCapabilities: ViewerCapabilities;
  /** ObjectDB pk of the viewer's active character; null if none puppeted. */
  actorCharacterId: number | null;
}

export function GroupStoryRequestPanel({
  covenantId,
  viewerCapabilities,
  actorCharacterId,
}: GroupStoryRequestPanelProps) {
  const { data: openRequest, isLoading } = useCovenantGroupStoryRequest(covenantId);
  const requestGM = useRequestGMForCovenant(covenantId, actorCharacterId ?? 0);
  const withdrawGM = useWithdrawGroupStoryRequest(covenantId, actorCharacterId ?? 0);
  const [message, setMessage] = useState('');
  const [showForm, setShowForm] = useState(false);

  // Only surface this panel to members who could plausibly act on it, or
  // when there's an existing open request worth showing to anyone who can see
  // the covenant page (recruiting status is not privacy-scoped, see #2119
  // leak analysis — covenant identity in the queue is not new exposure).
  if (isLoading) return null;
  if (!viewerCapabilities.can_request_gm && !openRequest) return null;

  function handleSubmit() {
    if (actorCharacterId === null) return;
    requestGM.mutate(message, {
      onSuccess: () => setMessage(''),
    });
    setShowForm(false);
  }

  function handleWithdraw() {
    if (openRequest) withdrawGM.mutate(openRequest.id);
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Recruiting a GM</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {openRequest ? (
          <div className="space-y-2" data-testid="open-gm-request">
            <p className="text-sm text-muted-foreground">
              An open ask for a GM has been posted
              {openRequest.message ? `: "${openRequest.message}"` : '.'}
            </p>
            {viewerCapabilities.can_request_gm && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleWithdraw}
                disabled={withdrawGM.isPending}
                data-testid="withdraw-gm-request-button"
              >
                {withdrawGM.isPending ? 'Withdrawing…' : 'Withdraw'}
              </Button>
            )}
          </div>
        ) : showForm ? (
          <div className="space-y-2">
            <label htmlFor="gm-request-message" className="sr-only">
              Message to prospective GMs
            </label>
            <Textarea
              id="gm-request-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Pitch your covenant to prospective GMs (visible to the GM pool)…"
              rows={3}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={handleSubmit}
                disabled={requestGM.isPending || actorCharacterId === null}
                data-testid="submit-gm-request-button"
              >
                {requestGM.isPending ? 'Posting…' : 'Post Request'}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <Button
            size="sm"
            onClick={() => setShowForm(true)}
            disabled={actorCharacterId === null}
            data-testid="request-gm-button"
          >
            Request a GM
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
