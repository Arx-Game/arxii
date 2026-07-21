import { Info, ScrollText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { CodexLinkRef } from '../types';
import { CodexInlineLink } from './CodexInlineLink';

interface ContentSectionProps {
  content: string;
  links?: CodexLinkRef[];
  onNavigate?: (entryId: number) => void;
}

const WIKILINK_RE = /\[\[([^\]]+)\]\]/g;

/**
 * Split content into text and link segments based on [[wikilink]] syntax.
 * Text segments are rendered through ReactMarkdown; link segments are
 * rendered as CodexInlineLink (accessible) or "???" (inaccessible).
 */
function renderContent(
  content: string,
  links: CodexLinkRef[],
  onNavigate?: (entryId: number) => void
): React.ReactNode[] {
  const segments: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;

  for (const match of content.matchAll(WIKILINK_RE)) {
    const matchText = match[0];
    const start = match.index ?? 0;

    // Text before the link
    if (start > lastIndex) {
      const textSegment = content.slice(lastIndex, start);
      segments.push(
        <ReactMarkdown key={key++} remarkPlugins={[remarkGfm]}>
          {textSegment}
        </ReactMarkdown>
      );
    }

    // Find the matching link ref
    const linkRef = links.find((l) => l.match_text === matchText);
    if (linkRef && linkRef.accessible && linkRef.entry_id !== null && onNavigate) {
      segments.push(
        <CodexInlineLink key={key++} entryId={linkRef.entry_id} onNavigate={onNavigate}>
          {linkRef.display_text}
        </CodexInlineLink>
      );
    } else if (linkRef && linkRef.accessible && linkRef.entry_id !== null) {
      // Accessible but no navigation callback — render as styled text
      segments.push(
        <span key={key++} className="text-primary underline decoration-dotted underline-offset-2">
          {linkRef.display_text}
        </span>
      );
    } else if (linkRef) {
      segments.push(
        <span
          key={key++}
          className="cursor-help italic text-muted-foreground"
          title="You have not yet discovered this."
        >
          ???
        </span>
      );
    } else {
      // No matching link ref — render the raw text
      segments.push(<span key={key++}>{matchText}</span>);
    }

    lastIndex = start + matchText.length;
  }

  // Remaining text after the last link
  if (lastIndex < content.length) {
    const textSegment = content.slice(lastIndex);
    segments.push(
      <ReactMarkdown key={key++} remarkPlugins={[remarkGfm]}>
        {textSegment}
      </ReactMarkdown>
    );
  }

  return segments;
}

export function LoreSection({ content, links, onNavigate }: ContentSectionProps) {
  return (
    <div className="rounded-lg border border-amber-200/50 bg-amber-50/50 p-4 shadow-inner dark:border-amber-900/30 dark:bg-amber-950/20">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
        <ScrollText className="h-3.5 w-3.5" />
        Lore
      </div>
      <div className="prose prose-sm dark:prose-invert max-w-none text-amber-950 dark:text-amber-100">
        {renderContent(content, links ?? [], onNavigate)}
      </div>
    </div>
  );
}

export function OOCSection({ content, links, onNavigate }: ContentSectionProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-100 p-4 dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-400">
        <Info className="h-3.5 w-3.5" />
        OOC
      </div>
      <div className="prose prose-sm dark:prose-invert max-w-none">
        {renderContent(content, links ?? [], onNavigate)}
      </div>
    </div>
  );
}
