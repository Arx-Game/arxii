import { Info, ScrollText } from 'lucide-react';

interface ContentSectionProps {
  content: string;
}

export function LoreSection({ content }: ContentSectionProps) {
  return (
    <div className="rounded-lg border border-amber-200/50 bg-amber-50/50 p-4 shadow-inner dark:border-amber-900/30 dark:bg-amber-950/20">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
        <ScrollText className="h-3.5 w-3.5" />
        Lore
      </div>
      <div className="prose prose-sm dark:prose-invert max-w-none text-amber-950 dark:text-amber-100">
        {content.split('\n').map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
      </div>
    </div>
  );
}

export function OOCSection({ content }: ContentSectionProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-100 p-4 dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-slate-400">
        <Info className="h-3.5 w-3.5" />
        OOC
      </div>
      <div className="prose prose-sm dark:prose-invert max-w-none">
        {content.split('\n').map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
      </div>
    </div>
  );
}
