import { X } from 'lucide-react';

export interface ConversationTabMeta {
  key: string;
  label: string;
  unreadCount: number;
}

export interface ConversationTabStripProps {
  roomLabel: string;
  roomUnreadCount: number;
  tabs: ConversationTabMeta[];
  /** Active conversation tab key; null = the room anchor tab. */
  activeKey: string | null;
  onSelect: (key: string | null) => void;
  onClose: (key: string) => void;
}

function UnreadBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="ml-1 rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
      {count}
    </span>
  );
}

/**
 * Tab strip of open conversations (#2165) — the room feed as the anchor tab
 * plus one closable tab per broken-out thread. Mirrors the multi-puppet
 * session tab bar directly above it (GameWindow.tsx); renders nothing until
 * at least one conversation tab is open.
 */
export function ConversationTabStrip({
  roomLabel,
  roomUnreadCount,
  tabs,
  activeKey,
  onSelect,
  onClose,
}: ConversationTabStripProps) {
  if (tabs.length === 0) return null;
  const tabClass = (isActive: boolean) =>
    `flex items-center whitespace-nowrap rounded-t px-2 py-1 text-sm ${
      isActive ? 'border-b-2 border-primary font-medium' : 'text-muted-foreground'
    }`;
  return (
    <div
      role="tablist"
      aria-label="Conversations"
      className="mb-2 flex gap-1 overflow-x-auto border-b"
    >
      <button
        role="tab"
        aria-selected={activeKey === null}
        onClick={() => onSelect(null)}
        className={tabClass(activeKey === null)}
      >
        {roomLabel}
        <UnreadBadge count={roomUnreadCount} />
      </button>
      {tabs.map((tab) => (
        <span key={tab.key} className="flex items-center">
          <button
            role="tab"
            aria-selected={activeKey === tab.key}
            onClick={() => onSelect(tab.key)}
            className={tabClass(activeKey === tab.key)}
          >
            {tab.label}
            <UnreadBadge count={tab.unreadCount} />
          </button>
          <button
            type="button"
            aria-label={`Close ${tab.label}`}
            onClick={() => onClose(tab.key)}
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  );
}
