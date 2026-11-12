import { useId } from 'react';
import { ArrowDown, ArrowUp, LogOut, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useChannelIdentitiesQuery, useLeaveChannel, useUpdateSubscription } from '../queries';
import type { ChannelNotificationLevel, JoinedChannel } from '../types';

const NOTIFICATION_OPTIONS: { value: ChannelNotificationLevel; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'badge', label: 'Unread count only' },
  { value: 'none', label: 'Nothing' },
];

/** Who the player speaks as in this channel: their own eligible characters only. */
export function IdentitySelect({ channel }: { channel: JoinedChannel }) {
  const sub = channel.subscription;
  const { data: identities } = useChannelIdentitiesQuery(channel.id, true);
  const update = useUpdateSubscription(channel.id);
  const value = sub.display_tenure ? String(sub.display_tenure) : undefined;
  return (
    <Select
      value={value}
      onValueChange={(next) =>
        update.mutate({ id: sub.id, patch: { display_tenure: Number(next) } })
      }
    >
      <SelectTrigger aria-label="Speak as" className="h-8 text-xs">
        <SelectValue placeholder="Speak as" />
      </SelectTrigger>
      <SelectContent>
        {(identities ?? []).map((identity) => (
          <SelectItem key={identity.id} value={String(identity.id)}>
            {identity.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

interface ChannelControlsProps {
  channel: JoinedChannel;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMove: (direction: -1 | 1) => void;
}

/** One lane's settings menu. */
export function ChannelControls({ channel, canMoveUp, canMoveDown, onMove }: ChannelControlsProps) {
  const sub = channel.subscription;
  const update = useUpdateSubscription(channel.id);
  const leave = useLeaveChannel();
  const muteId = useId();
  const notifyId = useId();
  const patch = (fields: Parameters<typeof update.mutate>[0]['patch']) =>
    update.mutate({ id: sub.id, patch: fields });

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          aria-label={`${channel.name} settings`}
        >
          <Settings2 className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 space-y-3 text-sm">
        <IdentitySelect channel={channel} />
        <div className="flex items-center justify-between">
          <Label htmlFor={muteId}>Mute</Label>
          <Switch
            id={muteId}
            checked={sub.muted ?? false}
            onCheckedChange={(muted) => patch({ muted })}
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={() => patch({ collapsed: !sub.collapsed })}
        >
          {sub.collapsed ? 'Expand' : 'Collapse'}
        </Button>
        <div className="space-y-1">
          <Label htmlFor={notifyId}>Notifications</Label>
          <Select
            value={sub.notification_level ?? 'badge'}
            onValueChange={(level) =>
              patch({ notification_level: level as ChannelNotificationLevel })
            }
          >
            <SelectTrigger id={notifyId} className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {NOTIFICATION_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            disabled={!canMoveUp}
            onClick={() => onMove(-1)}
          >
            <ArrowUp className="mr-1 h-3.5 w-3.5" />
            Move up
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            disabled={!canMoveDown}
            onClick={() => onMove(1)}
          >
            <ArrowDown className="mr-1 h-3.5 w-3.5" />
            Move down
          </Button>
        </div>
        <Button
          variant="destructive"
          size="sm"
          className="w-full"
          disabled={leave.isPending}
          onClick={() => leave.mutate(sub.id)}
        >
          <LogOut className="mr-1 h-3.5 w-3.5" />
          Leave
        </Button>
      </PopoverContent>
    </Popover>
  );
}
