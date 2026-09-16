/**
 * One collapsible section of the edit page (#3780). The header carries a highlight dot
 * while the section still holds an unfilled optional field, so a maintainer sees what
 * needs work without expanding everything. No explainer copy: a section's "+ Add" control
 * carries any needed explanation as a hover tooltip (`title`).
 */

import type { ReactNode } from 'react';
import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { cn } from '@/lib/utils';

interface EditorSectionProps {
  value: string;
  title: string;
  incomplete: boolean;
  tint?: 'gm';
  children: ReactNode;
}

export function EditorSection({ value, title, incomplete, tint, children }: EditorSectionProps) {
  return (
    <AccordionItem
      value={value}
      className={cn(
        'rounded-md border px-4',
        tint === 'gm' &&
          'border-amber-300 bg-amber-50/60 dark:border-amber-700 dark:bg-amber-950/20'
      )}
      data-testid={`section-${value}`}
    >
      <AccordionTrigger className="py-3 text-base font-semibold hover:no-underline">
        <span className="flex items-center gap-2">
          {title}
          {incomplete && (
            <span
              className="inline-block h-2 w-2 rounded-full bg-amber-500"
              aria-label="Has unfilled fields"
              data-testid={`dot-${value}`}
            />
          )}
        </span>
      </AccordionTrigger>
      <AccordionContent className="space-y-3 pb-4">{children}</AccordionContent>
    </AccordionItem>
  );
}
