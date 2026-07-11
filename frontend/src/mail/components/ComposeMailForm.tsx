import { useEffect, useState } from 'react';
import { useSendMail } from '../queries';
import type { PlayerMail } from '../types';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { SubmitButton } from '@/components/SubmitButton';
import { useQueryClient } from '@tanstack/react-query';
import TenureSearch from '@/components/TenureSearch';
import MyTenureSelect from '@/components/MyTenureSelect';

interface Props {
  replyTo?: PlayerMail | null;
  onSent?: () => void;
  /**
   * Pre-fill props for a "compose to a specific character" quick action
   * (#2160's character-card "Send a letter"). When `initialRecipientTenureId`
   * is set, the recipient row renders a static "To: {initialRecipientDisplay}"
   * label instead of `TenureSearch` — that component's display text is
   * internal state we can't hand it from outside.
   */
  initialRecipientTenureId?: number;
  initialRecipientDisplay?: string;
  /**
   * When set, hides `MyTenureSelect` and sends from this tenure — only pass
   * this when the sender is unambiguous (a single active tenure resolvable
   * from context); otherwise omit it and let the player pick among theirs.
   */
  fixedSenderTenureId?: number;
}

export function ComposeMailForm({
  replyTo,
  onSent,
  initialRecipientTenureId,
  initialRecipientDisplay,
  fixedSenderTenureId,
}: Props) {
  const [recipient, setRecipient] = useState<number | null>(initialRecipientTenureId ?? null);
  const [senderTenure, setSenderTenure] = useState<number | null>(fixedSenderTenureId ?? null);
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const sendMail = useSendMail();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (replyTo) {
      setRecipient(replyTo.sender_tenure);
      setSenderTenure(replyTo.recipient_tenure);
      const subj = replyTo.subject.startsWith('Re:') ? replyTo.subject : `Re: ${replyTo.subject}`;
      setSubject(subj);
      const quoted = replyTo.message
        .split('\n')
        .map((line) => `> ${line}`)
        .join('\n');
      setMessage(`\n\n${quoted}`);
    }
  }, [replyTo]);

  // Syncs the pre-filled recipient/sender when a parent hands us a new one
  // (e.g. the character-card "Send a letter" dialog is reused for a
  // different character without remounting this form).
  useEffect(() => {
    if (initialRecipientTenureId != null) {
      setRecipient(initialRecipientTenureId);
    }
  }, [initialRecipientTenureId]);

  useEffect(() => {
    if (fixedSenderTenureId != null) {
      setSenderTenure(fixedSenderTenureId);
    }
  }, [fixedSenderTenureId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipient || !senderTenure) return;
    sendMail.mutate(
      {
        recipient_tenure: recipient,
        sender_tenure: senderTenure,
        subject,
        message,
        in_reply_to: replyTo?.id,
      },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: ['mail'] });
          // Restore to the fixed pre-fill (if any) rather than blanking it —
          // a reused mounted form (dialog stays mounted while closed, see
          // JournalComposerDialog) must stay valid to send again.
          setRecipient(initialRecipientTenureId ?? null);
          setSenderTenure(fixedSenderTenureId ?? null);
          setSubject('');
          setMessage('');
          onSent?.();
        },
      }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="flex gap-2">
        {initialRecipientTenureId != null ? (
          <div className="flex w-64 flex-col justify-end pb-1">
            <span className="text-sm font-medium">To: {initialRecipientDisplay}</span>
          </div>
        ) : (
          <TenureSearch value={recipient} onChange={(id) => setRecipient(id)} />
        )}
        {fixedSenderTenureId == null && (
          <MyTenureSelect value={senderTenure} onChange={setSenderTenure} />
        )}
      </div>
      <Input placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
      <Textarea
        placeholder="Message (Markdown supported)"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
      />
      <SubmitButton disabled={!recipient || !senderTenure} isLoading={sendMail.isPending}>
        Send
      </SubmitButton>
    </form>
  );
}

export default ComposeMailForm;
