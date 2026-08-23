/**
 * BoardPanel (#3286) — read + post UI for a single bulletin board.
 *
 * Shared between the room panel (LOCATION board) and the OrgPage Board tab
 * (ORG board) — both resolve a `boardId` and pass it here. Posting/removing
 * dispatch through `post_to_board`/`remove_board_post` (the same Actions
 * `CmdBoard` uses on telnet); the server is the only authority on who may
 * post or remove — a refusal surfaces as a toast, nothing is optimistically
 * applied.
 */

import { useState } from 'react';
import { Pin, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { BOARD_KEYS, useBoardPostsQuery } from '@/boards/queries';

interface BoardPanelProps {
  boardId: number;
  boardName: string;
  /** The active puppet's ObjectDB/CharacterSheet pk; posting/removing disabled without one. */
  characterId?: number | null;
}

export function BoardPanel({ boardId, boardName, characterId }: BoardPanelProps) {
  const { data: posts = [] } = useBoardPostsQuery(boardId);
  const { mutate, isPending } = useDispatchPlayerAction(characterId ?? 0);
  const queryClient = useQueryClient();
  const [composeOpen, setComposeOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: BOARD_KEYS.posts(boardId) }).catch(() => {});
  };

  const handleResult = (result: { message?: string | null; success?: boolean | null }) => {
    if (isDispatchFailure(result)) {
      toast.error(result.message ?? 'That failed.');
      return;
    }
    if (result.message) toast.success(result.message);
    invalidate();
  };

  const handlePost = () => {
    if (!title.trim() || !body.trim()) return;
    mutate(
      {
        ref: { backend: 'registry', registry_key: 'post_to_board' },
        kwargs: { board_id: boardId, title: title.trim(), body: body.trim() },
      },
      {
        onSuccess: (result) => {
          handleResult(result);
          if (!isDispatchFailure(result)) {
            setTitle('');
            setBody('');
            setComposeOpen(false);
          }
        },
        onError: (error: Error) => toast.error(error.message),
      }
    );
  };

  const handleRemove = (postId: number) => {
    mutate(
      {
        ref: { backend: 'registry', registry_key: 'remove_board_post' },
        kwargs: { post_id: postId },
      },
      {
        onSuccess: handleResult,
        onError: (error: Error) => toast.error(error.message),
      }
    );
  };

  return (
    <div className="border-b px-3 py-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase text-muted-foreground">{boardName}</span>
        {characterId != null && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 gap-1 px-2 text-xs"
            onClick={() => setComposeOpen(true)}
          >
            <Pin className="h-3 w-3" />
            Post
          </Button>
        )}
      </div>
      {posts.length === 0 ? (
        <p className="text-xs text-muted-foreground">No notices posted yet.</p>
      ) : (
        <ul className="space-y-2">
          {posts.map((post) => (
            <li key={post.id} className="text-xs">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="font-semibold">{post.title}</span>{' '}
                  <span className="text-muted-foreground">by {post.author_display}</span>
                </div>
                {characterId != null && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-5 w-5 shrink-0 p-0"
                    disabled={isPending}
                    onClick={() => handleRemove(post.id)}
                    aria-label={`Remove ${post.title}`}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                )}
              </div>
              <p className="whitespace-pre-wrap text-muted-foreground">{post.body}</p>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={composeOpen} onOpenChange={setComposeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Post to {boardName}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={200}
            />
            <Textarea
              placeholder="Notice body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={5}
            />
            <Button
              className="w-full"
              disabled={isPending || !title.trim() || !body.trim()}
              onClick={handlePost}
            >
              Pin Notice
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
