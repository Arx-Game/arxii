import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { apiFetch } from '@/evennia_replacements/api';

/**
 * #3288 — the mandatory identity-free OOC disclosure of a concealed occupant.
 *
 * Rendered whenever the room's `has_unseen_presence` flag is true. Carries the
 * always-available report affordance: the report names nobody — the server
 * resolves who held concealment here into the staff-visible report, and the
 * reporter never learns the identity.
 */

interface UnseenPresenceRowProps {
  /** The viewer's active persona pk — the reporter identity for the report. */
  viewerPersonaId: number | null;
}

async function reportHiddenPresence(personaId: number, description: string): Promise<void> {
  const res = await apiFetch('/api/player-submissions/player-reports/hidden-presence/', {
    method: 'POST',
    body: JSON.stringify({
      reporter_persona: personaId,
      behavior_description: description,
    }),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? 'Failed to file the report.');
  }
}

export function UnseenPresenceRow({ viewerPersonaId }: UnseenPresenceRowProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [description, setDescription] = useState('');

  const report = useMutation({
    mutationFn: () => reportHiddenPresence(viewerPersonaId!, description),
    onSuccess: () => {
      setDialogOpen(false);
      setDescription('');
      toast.success('Report filed. Staff will review it; the presence stays anonymous to you.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <li data-testid="unseen-presence-row">
      <div className="flex items-center gap-2 rounded-md bg-destructive/10 px-1 py-0.5">
        <EyeOff className="h-4 w-4 text-destructive" />
        <span className="text-xs italic text-muted-foreground">Unseen presence</span>
        {viewerPersonaId != null && (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto h-5 px-1 text-[10px] text-destructive"
            onClick={() => setDialogOpen(true)}
          >
            Report
          </Button>
        )}
      </div>
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Report unseen presence</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Someone here is hidden. You will not learn who they are; staff will. Use this if a
            hidden presence is being used to make people uncomfortable.
          </p>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What happened, in your own words."
            rows={4}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={report.isPending || description.trim().length === 0}
              onClick={() => report.mutate()}
            >
              File report
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  );
}
