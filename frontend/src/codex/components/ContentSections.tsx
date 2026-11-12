import { Info, ScrollText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';
import { markdownProse } from '@/lib/markdownProse';
import type { CodexLinkRef } from '../types';
import { CodexInlineLink } from './CodexInlineLink';

interface ContentSectionProps {
  content: string;
  links?: CodexLinkRef[];
  onNavigate?: (entryId: number) => void;
}

// `[^[\\]]` rather than `[^\\]]`: excluding the opening bracket too means a run of
// brackets cannot be re-scanned from every position looking for a closing pair.
const WIKILINK_RE = /\[\[([^[\]]+)\]\]/g;

/** Where a wikilink sits in the Markdown source: a link to this fragment plus its index. */
const WIKILINK_HREF = '#codex-link-';

/** One `[[wikilink]]`: a link the reader may follow, a "???" they may not, or the raw text. */
function Wikilink({
  matchText,
  links,
  onNavigate,
}: {
  matchText: string;
  links: CodexLinkRef[];
  onNavigate?: (entryId: number) => void;
}) {
  const linkRef = links.find((l) => l.match_text === matchText);
  if (linkRef && linkRef.accessible && linkRef.entry_id !== null && onNavigate) {
    return (
      <CodexInlineLink entryId={linkRef.entry_id} onNavigate={onNavigate}>
        {linkRef.display_text}
      </CodexInlineLink>
    );
  }
  if (linkRef && linkRef.accessible && linkRef.entry_id !== null) {
    // Accessible but no navigation callback: styled text
    return (
      <span className="text-primary underline decoration-dotted underline-offset-2">
        {linkRef.display_text}
      </span>
    );
  }
  if (linkRef) {
    return (
      <span
        className="cursor-help italic text-muted-foreground"
        title="You have not yet discovered this."
      >
        ???
      </span>
    );
  }
  // No matching link ref: the raw text
  return <span>{matchText}</span>;
}

/**
 * The entry's text as one Markdown document, so the author's paragraphs stay
 * whole (#5090). Each `[[wikilink]]` is swapped for a Markdown link to a
 * numbered fragment before parsing and drawn by `Wikilink` where that link
 * lands, inside its sentence. Splitting the text at the links and rendering
 * each piece on its own, as this used to, broke a paragraph in two at every link.
 */
function renderContent(
  content: string,
  links: CodexLinkRef[],
  onNavigate?: (entryId: number) => void
): React.ReactNode {
  const matches: string[] = [];
  const source = content.replace(WIKILINK_RE, (matchText) => {
    matches.push(matchText);
    return `[link](${WIKILINK_HREF}${matches.length - 1})`;
  });
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => {
          const matchText = href?.startsWith(WIKILINK_HREF)
            ? matches[Number(href.slice(WIKILINK_HREF.length))]
            : undefined;
          return matchText ? (
            <Wikilink matchText={matchText} links={links} onNavigate={onNavigate} />
          ) : (
            <a href={href}>{children}</a>
          );
        },
      }}
    >
      {source}
    </ReactMarkdown>
  );
}

export function LoreSection({ content, links, onNavigate }: ContentSectionProps) {
  return (
    <div className="rounded-lg border border-amber-200/50 bg-amber-50/50 p-4 shadow-inner dark:border-amber-900/30 dark:bg-amber-950/20">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
        <ScrollText className="h-3.5 w-3.5" />
        Lore
      </div>
      <div className={cn('max-w-none text-sm text-amber-950 dark:text-amber-100', markdownProse)}>
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
      <div className={cn('max-w-none text-sm', markdownProse)}>
        {renderContent(content, links ?? [], onNavigate)}
      </div>
    </div>
  );
}
