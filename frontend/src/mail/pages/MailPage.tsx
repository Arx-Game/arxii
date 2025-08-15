import { useState } from 'react';
import ComposeMailForm from '../components/ComposeMailForm';
import ReceivedMailList from '../components/ReceivedMailList';
import type { PlayerMail } from '../types';

export function MailPage() {
  const [page, setPage] = useState(1);
  const [replyTo, setReplyTo] = useState<PlayerMail | null>(null);

  return (
    <div className="space-y-4">
      <ComposeMailForm replyTo={replyTo} onSent={() => setReplyTo(null)} />
      <ReceivedMailList page={page} onPageChange={setPage} onReply={(mail) => setReplyTo(mail)} />
    </div>
  );
}

export default MailPage;
