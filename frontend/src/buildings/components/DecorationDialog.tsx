import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

import { useDecorationTemplatesQuery } from '../queries';
import type { ManagerRoom, RoomBuilderActionKey } from '../types';

interface DecorationDialogProps {
  /** The room being decorated, or null to decorate the whole building. */
  targetRoom: ManagerRoom | null;
  /** The dispatch anchor (the target room itself, or the entry room for building-wide). */
  anchorRoomId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

/** Commission a decoration project from the admin-authored template catalog. */
export function DecorationDialog({
  targetRoom,
  anchorRoomId,
  open,
  onOpenChange,
  runAction,
}: DecorationDialogProps) {
  const [search, setSearch] = useState('');
  const templates = useDecorationTemplatesQuery(search, open);

  const commission = (templateId: number) => {
    runAction('commission_decoration', {
      room_id: anchorRoomId,
      template_id: templateId,
      target_room: targetRoom != null,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {targetRoom ? `Decorate ${targetRoom.name}` : 'Decorate the building'}
          </DialogTitle>
        </DialogHeader>
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search the catalog…"
        />
        <div className="flex max-h-96 flex-col gap-2 overflow-y-auto">
          {templates.isLoading && <p className="text-sm text-muted-foreground">Loading catalog…</p>}
          {(templates.data?.results ?? []).map((template) => (
            <div key={template.id} className="rounded-md border p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold">{template.name}</span>
                <Button size="sm" onClick={() => commission(template.id)}>
                  Commission ({template.base_cost})
                </Button>
              </div>
              {template.description && (
                <p className="mt-1 text-xs text-muted-foreground">{template.description}</p>
              )}
              <div className="mt-1 flex flex-wrap gap-1">
                {template.increments.map((increment) => (
                  <Badge key={increment.category} variant="outline">
                    +{increment.value} {increment.category}
                  </Badge>
                ))}
                {template.tier_prerequisites.map((prerequisite) => (
                  <Badge key={prerequisite} variant="secondary">
                    requires {prerequisite}
                  </Badge>
                ))}
              </div>
            </div>
          ))}
          {templates.data && templates.data.results.length === 0 && (
            <p className="text-sm text-muted-foreground">No templates match.</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
