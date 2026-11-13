/**
 * The character's missives (#3289): received letters grouped by the face they were
 * addressed to ("To <persona>"), then the ones it sent. Opening an unread letter
 * marks it read (`read_missive`).
 */
import { toast } from 'sonner';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { useMissiveAction } from '../queries';
import type { AttachmentResolution, Missive } from '../types';

const RESOLUTION_LABEL: Record<AttachmentResolution, string> = {
  pending: 'Waiting',
  accepted: 'Accepted',
  refused: 'Refused',
};

interface MissiveGroup {
  key: string;
  heading: string;
  rows: Missive[];
}

function groupMissives(missives: Missive[]): MissiveGroup[] {
  const received = new Map<number, Missive[]>();
  const sent: Missive[] = [];
  for (const missive of missives) {
    if (missive.direction === 'sent') {
      sent.push(missive);
      continue;
    }
    const rows = received.get(missive.own_persona_id) ?? [];
    rows.push(missive);
    received.set(missive.own_persona_id, rows);
  }
  const groups: MissiveGroup[] = [...received.entries()].map(([personaId, rows]) => ({
    key: `to-${personaId}`,
    heading: `To ${rows[0].own_persona_name}`,
    rows,
  }));
  if (sent.length > 0) groups.push({ key: 'sent', heading: 'Sent', rows: sent });
  return groups;
}

interface MissiveListProps {
  missives: Missive[];
  characterId: number;
  onReply: (missive: Missive) => void;
}

export function MissiveList({ missives, characterId, onReply }: MissiveListProps) {
  const action = useMissiveAction(characterId);

  if (missives.length === 0) {
    return <p className="text-sm text-muted-foreground">No missives.</p>;
  }

  const byId = new Map(missives.map((m) => [String(m.id), m]));

  const handleOpen = (value: string) => {
    const missive = byId.get(value);
    if (missive && missive.direction === 'received' && !missive.is_read) {
      action.mutate(
        { key: 'read_missive', kwargs: { missive_id: missive.id } },
        { onError: (err) => toast.error(err.message) }
      );
    }
  };

  const resolve = (missive: Missive, key: 'accept_missive' | 'refuse_missive') =>
    action.mutate(
      { key, kwargs: { missive_id: missive.id } },
      {
        onSuccess: ({ message }) => {
          if (message) toast.success(message);
        },
        onError: (err) => toast.error(err.message),
      }
    );

  return (
    <Accordion type="single" collapsible onValueChange={handleOpen} className="space-y-4">
      {groupMissives(missives).map((group) => (
        <section key={group.key}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {group.heading}
          </h3>
          {group.rows.map((missive) => {
            const unread = missive.direction === 'received' && !missive.is_read;
            const hasPending =
              missive.direction === 'received' &&
              missive.attachments.some((a) => a.resolution === 'pending');
            return (
              <AccordionItem key={missive.id} value={String(missive.id)}>
                <AccordionTrigger className="py-2 text-left text-sm">
                  <span className="flex min-w-0 items-center gap-2">
                    {unread && (
                      <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden />
                    )}
                    <span className={unread ? 'truncate font-semibold' : 'truncate font-normal'}>
                      {missive.counterpart_name}
                    </span>
                  </span>
                </AccordionTrigger>
                <AccordionContent className="space-y-3">
                  <p className="text-xs text-muted-foreground">
                    {[missive.ic_date, missive.method_name].filter(Boolean).join(', ')}
                  </p>
                  <p className="whitespace-pre-wrap">{missive.body}</p>
                  {missive.attachments.length > 0 && (
                    <ul className="space-y-1 text-xs">
                      {missive.attachments.map((attachment) => (
                        <li key={attachment.id}>
                          {attachment.label} ({RESOLUTION_LABEL[attachment.resolution]})
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="flex flex-wrap gap-2">
                    {hasPending && (
                      <>
                        <Button
                          type="button"
                          size="sm"
                          disabled={action.isPending}
                          onClick={() => resolve(missive, 'accept_missive')}
                        >
                          Accept
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={action.isPending}
                          onClick={() => resolve(missive, 'refuse_missive')}
                        >
                          Refuse
                        </Button>
                      </>
                    )}
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => onReply(missive)}
                    >
                      Reply
                    </Button>
                  </div>
                </AccordionContent>
              </AccordionItem>
            );
          })}
        </section>
      ))}
    </Accordion>
  );
}
