import { useState } from 'react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { useBanChannelAuthor, useDeleteChannelMessage } from '../queries';

const BAN_REASON_MAX = 500;

type Pending = 'delete' | 'ban' | null;

/** Staff-only Delete and Ban on one channel message, each behind a confirm. */
export function MessageModeration({
  channelId,
  messageId,
}: {
  channelId: number;
  messageId: number;
}) {
  const [pending, setPending] = useState<Pending>(null);
  const [reason, setReason] = useState('');
  const remove = useDeleteChannelMessage(channelId);
  const ban = useBanChannelAuthor();

  const close = () => {
    setPending(null);
    setReason('');
  };

  return (
    <span className="ml-2 inline-flex gap-2 text-xs text-muted-foreground">
      <button type="button" className="hover:text-destructive" onClick={() => setPending('delete')}>
        Delete
      </button>
      <button type="button" className="hover:text-destructive" onClick={() => setPending('ban')}>
        Ban
      </button>
      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && close()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending === 'ban' ? 'Ban this author from the channel?' : 'Delete this message?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending === 'ban'
                ? 'They leave the channel and cannot rejoin.'
                : 'This cannot be undone.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {pending === 'ban' ? (
            <Input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={BAN_REASON_MAX}
              placeholder="Reason"
              aria-label="Reason"
            />
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel onClick={close}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pending === 'ban') ban.mutate({ messageId, reason: reason.trim() });
                else remove.mutate(messageId);
                close();
              }}
            >
              {pending === 'ban' ? 'Ban' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </span>
  );
}
