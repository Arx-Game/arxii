import { useEffect, useState } from 'react';
import { useSendMail, useTenureSearch } from '../queries';
import type { PlayerMail } from '../types';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { useQueryClient } from '@tanstack/react-query';

interface Props {
  replyTo?: PlayerMail | null;
  onSent?: () => void;
}

export function ComposeMailForm({ replyTo, onSent }: Props) {
  const [recipient, setRecipient] = useState<number | null>(null);
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [search, setSearch] = useState('');
  const { data: results } = useTenureSearch(search);
  const sendMail = useSendMail();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (replyTo) {
      setRecipient(replyTo.sender_tenure);
      const subj = replyTo.subject.startsWith('Re:') ? replyTo.subject : `Re: ${replyTo.subject}`;
      setSubject(subj);
      const quoted = replyTo.message
        .split('\n')
        .map((line) => `> ${line}`)
        .join('\n');
      setMessage(`\n\n${quoted}`);
      if (replyTo.sender_display) {
        setSearch(replyTo.sender_display);
      }
    }
  }, [replyTo]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipient) return;
    sendMail.mutate(
      {
        recipient_tenure: recipient,
        subject,
        message,
        in_reply_to: replyTo?.id,
      },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: ['mail'] });
          setRecipient(null);
          setSubject('');
          setMessage('');
          setSearch('');
          onSent?.();
        },
      }
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <Input
        placeholder="Search character"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {results?.results.length ? (
        <ul className="rounded border">
          {results.results.map((opt) => (
            <li key={opt.id}>
              <Button
                type="button"
                variant={recipient === opt.id ? 'default' : 'ghost'}
                className="w-full justify-start"
                onClick={() => {
                  setRecipient(opt.id);
                  setSearch(opt.display_name);
                }}
              >
                {opt.display_name}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <Input placeholder="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
      <Textarea
        placeholder="Message (Markdown supported)"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
      />
      <Button type="submit" disabled={!recipient}>
        Send
      </Button>
    </form>
  );
}

export default ComposeMailForm;
