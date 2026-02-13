import { MessageSquare } from 'lucide-react';

export function ConversationSidebar() {
  return (
    <div className="flex flex-col">
      <div className="border-b px-3 py-2">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">Conversations</h3>
      </div>
      <div className="flex-1">
        <button className="flex w-full items-center gap-2 bg-accent px-3 py-2 text-sm">
          <MessageSquare className="h-4 w-4" />
          <span className="font-medium">Room</span>
        </button>
      </div>
    </div>
  );
}
