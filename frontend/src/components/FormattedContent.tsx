import React, { useMemo } from 'react';

import { type Segment, parseFormattedContent } from '@/lib/formatParser';
import { cn } from '@/lib/utils';
import { markMatches, useFeedFind } from '@/game/feedFind';

/*
 * The index IS the identity of a segment here, not a fallback key.
 *
 * Segments are parsed positionally out of `content`, and the whole list is
 * rebuilt whenever that string changes, so a segment cannot move relative to its
 * neighbours and none of them holds state. A key built from the segment text
 * would be strictly worse: repeated words would collide.
 *
 * Wrapping lives here, once (#3862). Every reader that renders a message body
 * (PoseUnit, ExplorationReader, SceneMessages) goes through this wrapper, so an
 * unbroken run of characters breaks at the column's edge in all of them
 * instead of widening the feed sideways. `overflow-wrap: anywhere` rather than
 * `break-word`: only `anywhere` lets the run shrink a flex child's min-content
 * width, and the feed column is a flex child.
 */

interface FormattedContentProps {
  content: string;
  className?: string;
}

export const FormattedContent = React.memo(function FormattedContent({
  content,
  className,
}: FormattedContentProps) {
  const segments = useMemo(() => parseFormattedContent(content), [content]);
  // Find in this session (#4129): the needle the rail's find box holds; each
  // match is marked where the text is drawn, inside whatever styling it has.
  const find = useFeedFind();
  return (
    <span className={cn('[overflow-wrap:anywhere]', className)}>
      {segments.map((segment: Segment, i: number) => {
        const text = markMatches(segment.content, find);
        switch (segment.type) {
          case 'bold':
            return <strong key={i}>{text}</strong>;
          case 'italic':
            return <em key={i}>{text}</em>;
          case 'strikethrough':
            return <del key={i}>{text}</del>;
          case 'color':
            return (
              <span key={i} style={{ color: segment.hex }}>
                {text}
              </span>
            );
          case 'link':
            return (
              <a
                key={i}
                href={segment.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 underline hover:text-blue-700"
              >
                {text}
              </a>
            );
          default:
            return <span key={i}>{text}</span>;
        }
      })}
    </span>
  );
});
