import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useMailQuery } from '../queries';
import type { PlayerMail } from '../types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface Props {
  page: number;
  onPageChange: (page: number) => void;
  onReply: (mail: PlayerMail) => void;
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
      {data?.results.map((mail) => (
        <Card key={mail.id} className="p-4">
          <CardHeader className="mb-2 flex items-center justify-between p-0">
            <CardTitle>{mail.subject}</CardTitle>
            {mail.sender_tenure && (
              <Button size="sm" onClick={() => onReply(mail)}>
                Reply
              </Button>
            )}
          </CardHeader>
          <CardContent className="p-0">
            <p className="text-sm text-muted-foreground">
              From {mail.sender_display} on {new Date(mail.sent_date).toLocaleString()}
            </p>
            <div className="prose mt-2 max-w-none text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{mail.message}</ReactMarkdown>
            </div>
          </CardContent>
        </Card>
      ))}
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
