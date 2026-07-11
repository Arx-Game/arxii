import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useMailQuery, useMarkMailRead } from '../queries';
import type { PlayerMail } from '../types';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface Props {
  page: number;
  onPageChange: (page: number) => void;
  onReply: (mail: PlayerMail) => void;
}

interface MailRowProps {
  mail: PlayerMail;
  onReply: (mail: PlayerMail) => void;
}

function MailRow({ mail, onReply }: MailRowProps) {
  const isUnread = mail.read_date === null;
  const { mutate: markRead } = useMarkMailRead(mail.id);

  return (
    <AccordionItem value={String(mail.id)} className="border-none">
      <Card className="p-4">
        <AccordionTrigger
          className="p-0 hover:no-underline"
          onClick={() => {
            if (isUnread) markRead();
          }}
        >
          <span className="flex items-center gap-2 text-left">
            {isUnread && (
              <span className="h-2 w-2 shrink-0 rounded-full bg-red-500" aria-label="Unread" />
            )}
            <span className={cn(isUnread && 'font-medium')}>{mail.subject}</span>
          </span>
        </AccordionTrigger>
        <AccordionContent className="p-0 pt-2">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              From {mail.sender_display} on {new Date(mail.sent_date).toLocaleString()}
            </p>
            {mail.sender_tenure && (
              <Button size="sm" onClick={() => onReply(mail)}>
                Reply
              </Button>
            )}
          </div>
          <div className="prose mt-2 max-w-none text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{mail.message}</ReactMarkdown>
          </div>
        </AccordionContent>
      </Card>
    </AccordionItem>
  );
}

export function ReceivedMailList({ page, onPageChange, onReply }: Props) {
  const { data } = useMailQuery(page);

  const nextPage = () => {
    if (data?.next) onPageChange(page + 1);
  };

  const prevPage = () => {
    if (data?.previous) onPageChange(page - 1);
  };

  return (
    <div className="space-y-2">
      <Accordion type="multiple" className="space-y-2">
        {data?.results.map((mail) => (
          <MailRow key={mail.id} mail={mail} onReply={onReply} />
        ))}
      </Accordion>
      <div className="flex gap-2">
        <Button onClick={prevPage} disabled={!data?.previous}>
          Previous
        </Button>
        <Button onClick={nextPage} disabled={!data?.next}>
          Next
        </Button>
      </div>
    </div>
  );
}

export default ReceivedMailList;
