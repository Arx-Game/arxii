import { useEffect, useState } from 'react';
import { useSendMail } from '../queries';
import type { PlayerMail } from '../types';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { useQueryClient } from '@tanstack/react-query';
import TenureSearch from '@/components/TenureSearch';
import MyTenureSelect from '@/components/MyTenureSelect';

interface Props {
  replyTo?: PlayerMail | null;
  onSent?: () => void;
}

export function ComposeMailForm({ replyTo, onSent }: Props) {
  const [recipient, setRecipient] = useState<number | null>(null);
  const [senderTenure, setSenderTenure] = useState<number | null>(null);
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
          setRecipient(null);
          setSenderTenure(null);
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
        <TenureSearch value={recipient} onChange={(id) => setRecipient(id)} />
        <MyTenureSelect value={senderTenure} onChange={setSenderTenure} />
      </div>
      <Input placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
      <Textarea
        placeholder="Message (Markdown supported)"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
      />
      <Button type="submit" disabled={!recipient || !senderTenure}>
        Send
      </Button>
    </form>
  );
}

export default ComposeMailForm;
