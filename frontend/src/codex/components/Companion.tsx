import { Fragment } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { CodexCompanionGroup, CodexCompanionItem, CodexCompanionSection } from '../types';

/**
 * The companion (#4198): what an entry's owner shows beside the prose. The rail holds
 * what scans (a date, a name, a card); a section holds a story. A line links to another
 * entry when it may be opened, or down to its own section.
 */
interface RailProps {
  groups: CodexCompanionGroup[];
  onNavigate: (entryId: number) => void;
}

function scrollTo(anchor: string) {
  document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function RailItem({
  item,
  onNavigate,
}: {
  item: CodexCompanionItem;
  onNavigate: RailProps['onNavigate'];
}) {
  if (item.entry_id !== null) {
    const entryId = item.entry_id;
    return (
      <button type="button" className="text-left" onClick={() => onNavigate(entryId)}>
        {item.text}
      </button>
    );
  }
  if (item.anchor !== null) {
    const anchor = item.anchor;
    return (
      <a
        href={`#${anchor}`}
        onClick={(event) => {
          event.preventDefault();
          scrollTo(anchor);
        }}
      >
        {item.text}
      </a>
    );
  }
  return <span>{item.text}</span>;
}

export function CompanionRail({ groups, onNavigate }: RailProps) {
  return (
    <aside className="codex-rail" aria-label="At a glance">
      {groups.map((group) => (
        <div key={group.label}>
          <div className="codex-rail-label">{group.label}</div>
          {group.items.map((item, index) => (
            <Fragment key={`${item.text}-${index}`}>
              {index > 0 && ', '}
              <RailItem item={item} onNavigate={onNavigate} />
            </Fragment>
          ))}
        </div>
      ))}
    </aside>
  );
}

interface SectionsProps {
  sections: CodexCompanionSection[];
  onNavigate: (entryId: number) => void;
}

export function CompanionSections({ sections, onNavigate }: SectionsProps) {
  return (
    <>
      {sections.map((section) => (
        <section key={section.anchor} id={section.anchor} className="codex-section space-y-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="codex-section-label">{section.label}</span>
            {section.entry_id !== null ? (
              <button
                type="button"
                className="font-semibold"
                onClick={() => onNavigate(section.entry_id as number)}
              >
                {section.name}
              </button>
            ) : (
              <span className="font-semibold">{section.name}</span>
            )}
            {section.when && <span className="text-sm text-muted-foreground">{section.when}</span>}
          </div>
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{section.body}</ReactMarkdown>
          </div>
        </section>
      ))}
    </>
  );
}
