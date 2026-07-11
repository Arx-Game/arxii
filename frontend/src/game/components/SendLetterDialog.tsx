/**
 * SendLetterDialog — thin Dialog wrapper around `ComposeMailForm`, pre-addressed
 * to a character from the character-card "Send a letter" quick action (#2160).
 *
 * Externally controlled (`open`/`onClose`), matching `JournalComposerDialog`'s
 * pattern rather than owning its own trigger — `CharacterCardDrawer` opens it
 * from its own quick-action button.
 *
 * `recipientTenureId`/`recipientDisplay` come from the card's resolved live
 * tenure (`entry.tenures.find(t => t.end_date === null)`) — the card only
 * offers this action when a live tenure exists (a vacant character has no one
 * to address), so both are always required here. `senderTenureId` is optional:
 * only pass it when the viewer's own current tenure is unambiguous from
 * context; otherwise omit it and `ComposeMailForm` falls back to
 * `MyTenureSelect` so the player picks among their own tenures.
 */
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { ComposeMailForm } from '@/mail/components/ComposeMailForm';

interface SendLetterDialogProps {
  open: boolean;
  onClose: () => void;
  /** The pre-addressed recipient's live `RosterTenure` id. */
  recipientTenureId: number;
  /** The pre-addressed recipient's display name, shown as "To: {name}". */
  recipientDisplay: string;
  /** The viewer's own tenure id, when unambiguous — hides `MyTenureSelect`. */
  senderTenureId?: number;
}

export function SendLetterDialog({
  open,
  onClose,
  recipientTenureId,
  recipientDisplay,
  senderTenureId,
}: SendLetterDialogProps) {
  function handleOpenChange(isOpen: boolean) {
    if (!isOpen) onClose();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send a Letter to {recipientDisplay}</DialogTitle>
        </DialogHeader>
        <ComposeMailForm
          initialRecipientTenureId={recipientTenureId}
          initialRecipientDisplay={recipientDisplay}
          fixedSenderTenureId={senderTenureId}
          onSent={() => {
            toast.success(`Letter sent to ${recipientDisplay}.`);
            onClose();
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
