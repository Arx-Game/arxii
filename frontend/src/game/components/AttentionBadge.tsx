const MAX_SHOWN = 99;

/**
 * Two-tier attention indicator (#2166 Decision 4a) -- direct (unseen
 * whisper/@-target aimed at this character) badges a small red numeric
 * count, mirroring `ConversationTabStrip`'s `UnreadBadge`; ambient (any
 * other unread) shows a muted dot; neither renders nothing.
 *
 * Extracted here (#3774) from the byte-identical copies that lived in
 * GameTopBar and GameWindow, and capped: `direct` now carries a server-side
 * count that can reach three digits, which overflows the pill. Before #3774
 * it could only count what one browser session had received, so nothing could.
 */
export function AttentionBadge({ direct, ambient }: { direct: number; ambient: boolean }) {
  if (direct > 0) {
    return (
      <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
        {direct > MAX_SHOWN ? `${MAX_SHOWN}+` : direct}
      </span>
    );
  }
  if (ambient) {
    return (
      <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-muted-foreground/60" />
    );
  }
  return null;
}
