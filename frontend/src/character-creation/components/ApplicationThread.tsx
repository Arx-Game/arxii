import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

import type { ApplicationComment, DraftApplicationDetail } from '../types';

interface ApplicationThreadProps {
  application: DraftApplicationDetail;
  onAddComment: (text: string) => void;
  isAddingComment?: boolean;
  readOnly?: boolean;
}

function StatusChangeEntry({ comment }: { comment: ApplicationComment }) {
  return (
    <div className="flex items-center gap-2 py-2">
      <div className="flex-1 border-t" />
      <span className="text-xs text-muted-foreground">{comment.text}</span>
      <span className="text-xs text-muted-foreground">
        {new Date(comment.created_at).toLocaleDateString()}
      </span>
      <div className="flex-1 border-t" />
    </div>
  );
}

function MessageEntry({ comment }: { comment: ApplicationComment }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">{comment.author_name ?? 'System'}</span>
          <span className="text-xs text-muted-foreground">
            {new Date(comment.created_at).toLocaleString()}
          </span>
        </div>
        <p className="whitespace-pre-wrap text-sm">{comment.text}</p>
      </CardContent>
    </Card>
  );
}

export function ApplicationThread({
  application,
  onAddComment,
  isAddingComment = false,
  readOnly = false,
}: ApplicationThreadProps) {
  const [commentText, setCommentText] = useState('');

  const handleSubmit = () => {
    if (!commentText.trim()) return;
    onAddComment(commentText);
    setCommentText('');
  };

  return (
    <div className="space-y-4">
      {application.submission_notes && (
        <Card>
          <CardContent className="pt-4">
            <p className="mb-1 text-sm text-muted-foreground">Submission Notes</p>
            <p className="text-sm">{application.submission_notes}</p>
          </CardContent>
        </Card>
      )}

      {application.comments.map((comment) => (
        <div key={comment.id}>
          {comment.comment_type === 'status_change' ? (
            <StatusChangeEntry comment={comment} />
          ) : (
            <MessageEntry comment={comment} />
          )}
        </div>
      ))}

      {!readOnly && (
        <div className="flex gap-2">
          <Textarea
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            placeholder="Add a comment..."
            className="min-h-[80px]"
          />
          <Button
            onClick={handleSubmit}
            disabled={!commentText.trim() || isAddingComment}
            className="self-end"
          >
            {isAddingComment ? 'Sending...' : 'Send'}
          </Button>
        </div>
      )}
    </div>
  );
}
