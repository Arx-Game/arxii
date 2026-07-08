import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { listRoles, listOffers, createSummons } from '@/npc_services/api';

interface GiveMissionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  targetPersonaId: number;
  targetPersonaName: string;
}

/**
 * Mid-scene GM "Give mission" dialog (#2050).
 *
 * A GM picks an NPC role → MISSION-kind offer → writes an IC message and
 * optional deadline. The summons is created via POST /api/npc-services/summons/.
 */
export function GiveMissionDialog({
  open,
  onOpenChange,
  targetPersonaId,
  targetPersonaName,
}: GiveMissionDialogProps) {
  const queryClient = useQueryClient();
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [selectedOfferId, setSelectedOfferId] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const [expiresAt, setExpiresAt] = useState('');

  const { data: rolesData } = useQuery({
    queryKey: ['npc-roles', 'give-mission'],
    queryFn: () => listRoles({ page_size: 100 }),
    enabled: open,
  });

  const { data: offersData } = useQuery({
    queryKey: ['npc-offers', 'give-mission', selectedRoleId],
    queryFn: () =>
      listOffers({ role: selectedRoleId ?? undefined, kind: 'mission', page_size: 100 }),
    enabled: open && selectedRoleId !== null,
  });

  const mutation = useMutation({
    mutationFn: createSummons,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['npc-summons'] });
      onOpenChange(false);
      setSelectedRoleId(null);
      setSelectedOfferId(null);
      setMessage('');
      setExpiresAt('');
    },
  });

  const handleSubmit = () => {
    if (selectedOfferId === null) return;
    mutation.mutate({
      offer_id: selectedOfferId,
      target_persona_id: targetPersonaId,
      message: message || undefined,
      expires_at: expiresAt || null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Give mission to {targetPersonaName}</DialogTitle>
          <DialogDescription>
            Direct a mission offer at this character. They will see it as a summons in their journal
            and can accept or decline.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="role-select">NPC Role</Label>
            <select
              id="role-select"
              className="w-full rounded border border-input bg-background px-3 py-2"
              value={selectedRoleId ?? ''}
              onChange={(e) => {
                setSelectedRoleId(Number(e.target.value) || null);
                setSelectedOfferId(null);
              }}
            >
              <option value="">Select a role…</option>
              {(rolesData?.results ?? []).map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </select>
          </div>
          {selectedRoleId !== null && (
            <div className="space-y-2">
              <Label htmlFor="offer-select">Mission Offer</Label>
              <select
                id="offer-select"
                className="w-full rounded border border-input bg-background px-3 py-2"
                value={selectedOfferId ?? ''}
                onChange={(e) => setSelectedOfferId(Number(e.target.value) || null)}
              >
                <option value="">Select an offer…</option>
                {(offersData?.results ?? []).map((offer) => (
                  <option key={offer.id} value={offer.id}>
                    {offer.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="summons-message">IC Message (optional)</Label>
            <Textarea
              id="summons-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="What the servant learns of the master's wish…"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="summons-deadline">Deadline (optional)</Label>
            <Input
              id="summons-deadline"
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={selectedOfferId === null || mutation.isPending} onClick={handleSubmit}>
            {mutation.isPending ? 'Sending…' : 'Send Summons'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
