import { Link } from 'react-router-dom';
import { ExternalLink, Loader2 } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useCodexEntry } from '../queries';

interface CodexModalProps {
  entryId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CodexModal({ entryId, open, onOpenChange }: CodexModalProps) {
  const { data: entry, isLoading, isError } = useCodexEntry(entryId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : isError ? (
          <div className="py-4 text-center text-muted-foreground">Unable to load entry</div>
        ) : entry ? (
          <>
            <DialogHeader>
              <DialogTitle>{entry.name}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">{entry.summary}</p>
              <Button asChild variant="outline" size="sm">
                <Link to={`/codex?entry=${entry.id}`} onClick={() => onOpenChange(false)}>
                  <ExternalLink className="mr-2 h-4 w-4" />
                  View in Codex
                </Link>
              </Button>
            </div>
          </>
        ) : (
          <div className="py-4 text-center text-muted-foreground">Entry not found</div>
        )}
      </DialogContent>
    </Dialog>
  );
}
