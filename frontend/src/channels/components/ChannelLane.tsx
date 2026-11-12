import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ChevronDown, ChevronRight, Send } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { HiddenDivider } from '@/components/HiddenDivider';
import {
  useChannelMessagesQuery,
  useMarkChannelRead,
  useOpenLaneRegistration,
  usePostChannelMessage,
  useUpdateSubscription,
} from '../queries';
import type { ChannelMessage, JoinedChannel } from '../types';
import { ChannelControls, IdentitySelect } from './ChannelControls';
import { MessageModeration } from './MessageModeration';
import { useAccount } from '@/store/hooks';

const MARK_READ_COALESCE_MS = 1500;

type LaneRow =
  { kind: 'message'; message: ChannelMessage } | { kind: 'hidden'; firstId: number; count: number };

/** Oldest first; each run of consecutive hidden rows folds into one row. */
function laneRows(newestFirst: ChannelMessage[]): LaneRow[] {
  const rows: LaneRow[] = [];
  for (const message of [...newestFirst].reverse()) {
    const last = rows[rows.length - 1];
    if (message.is_hidden) {
      if (last?.kind === 'hidden') last.count += 1;
      else rows.push({ kind: 'hidden', firstId: message.id, count: 1 });
    } else {
      rows.push({ kind: 'message', message });
    }
  }
  return rows;
}

function Composer({ channelId }: { channelId: number }) {
  const [body, setBody] = useState('');
  const post = usePostChannelMessage(channelId);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const text = body.trim();
    if (!text) return;
    post.mutate(text, { onSuccess: () => setBody('') });
  };
  return (
    <form onSubmit={submit} className="flex gap-1">
      <Input
        value={body}
        onChange={(event) => setBody(event.target.value)}
        aria-label="Message"
        className="h-8 text-sm"
      />
      <Button
        type="submit"
        size="icon"
        className="h-8 w-8 shrink-0"
        aria-label="Send"
        disabled={post.isPending || !body.trim()}
      >
        <Send className="h-3.5 w-3.5" />
      </Button>
    </form>
  );
}

interface ChannelLaneProps {
  channel: JoinedChannel;
  /** Whether the panel holding this lane is on screen (sidebar mode or page). */
  active: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMove: (direction: -1 | 1) => void;
}

export function ChannelLane({ channel, active, canMoveUp, canMoveDown, onMove }: ChannelLaneProps) {
  const sub = channel.subscription;
  const collapsed = sub.collapsed ?? false;
  const open = active && !collapsed;
  useOpenLaneRegistration(channel.id, open);

  const { data } = useChannelMessagesQuery(channel.id, open);
  const update = useUpdateSubscription(channel.id);
  const { mutate: markRead } = useMarkChannelRead(channel.id);
  const isStaff = useAccount()?.is_staff ?? false;
  const newest = data?.results[0];
  const newestId = newest?.id;
  const newestIsOwn = newest?.is_own ?? false;

  // Reading a lane marks it read: at once when it opens with unread, and, while it
  // stays open, once per burst of other people's messages (coalesced). A pending
  // mark is flushed when the lane closes or unmounts.
  const seenNewest = useRef<number | undefined>(undefined);
  const pendingMark = useRef<number | null>(null);
  useEffect(() => {
    if (!open) return;
    const changed = seenNewest.current !== undefined && newestId !== seenNewest.current;
    seenNewest.current = newestId;
    if (sub.unread_count > 0) {
      if (pendingMark.current !== null) window.clearTimeout(pendingMark.current);
      pendingMark.current = null;
      markRead(sub.id);
      return;
    }
    if (!changed || newestIsOwn) return;
    if (pendingMark.current !== null) window.clearTimeout(pendingMark.current);
    pendingMark.current = window.setTimeout(() => {
      pendingMark.current = null;
      markRead(sub.id);
    }, MARK_READ_COALESCE_MS);
  }, [open, newestId, newestIsOwn, sub.unread_count, sub.id, markRead]);
  useEffect(() => {
    if (!open) return;
    return () => {
      if (pendingMark.current === null) return;
      window.clearTimeout(pendingMark.current);
      pendingMark.current = null;
      markRead(sub.id);
    };
  }, [open, sub.id, markRead]);

  return (
    <section className="rounded border" aria-label={channel.name}>
      <header className="flex items-center gap-1 px-2 py-1">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-1 text-left text-sm font-medium"
          aria-expanded={!collapsed}
          onClick={() => update.mutate({ id: sub.id, patch: { collapsed: !collapsed } })}
        >
          {collapsed ? (
            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          )}
          <span className="truncate">{channel.name}</span>
          {sub.unread_count > 0 && !sub.muted && sub.notification_level !== 'none' ? (
            <Badge
              variant="destructive"
              className="ml-1 h-5 min-w-5 px-1 text-xs"
              data-testid="channel-unread"
            >
              {sub.unread_count}
            </Badge>
          ) : null}
        </button>
        <ChannelControls
          channel={channel}
          canMoveUp={canMoveUp}
          canMoveDown={canMoveDown}
          onMove={onMove}
        />
      </header>
      {collapsed ? null : (
        <div className="space-y-2 border-t px-2 py-2">
          <ol className="max-h-72 space-y-1 overflow-y-auto text-sm" data-testid="channel-messages">
            {laneRows(data?.results ?? []).map((row) =>
              row.kind === 'hidden' ? (
                <li key={`hidden-${row.firstId}`}>
                  <HiddenDivider label={`${row.count} hidden`} />
                </li>
              ) : (
                <li key={row.message.id} className="group [overflow-wrap:anywhere]">
                  <span className="font-medium">{row.message.speaker}</span>{' '}
                  <span>{row.message.body}</span>
                  {isStaff ? (
                    <MessageModeration channelId={channel.id} messageId={row.message.id} />
                  ) : null}
                </li>
              )
            )}
          </ol>
          {sub.display_tenure ? (
            <Composer channelId={channel.id} />
          ) : (
            <IdentitySelect channel={channel} />
          )}
        </div>
      )}
    </section>
  );
}
