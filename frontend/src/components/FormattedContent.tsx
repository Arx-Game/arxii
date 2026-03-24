import { parseFormattedContent } from '@/lib/formatParser';

interface FormattedContentProps {
  content: string;
  className?: string;
}

export function FormattedContent({ content, className }: FormattedContentProps) {
  const segments = parseFormattedContent(content);
  return (
    <span className={className}>
      {segments.map((segment, i) => {
        switch (segment.type) {
          case 'bold':
            return <strong key={i}>{segment.content}</strong>;
          case 'italic':
            return <em key={i}>{segment.content}</em>;
          case 'strikethrough':
            return <del key={i}>{segment.content}</del>;
          case 'color':
            return (
              <span key={i} style={{ color: segment.hex }}>
                {segment.content}
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
                {segment.content}
              </a>
            );
          default:
            return <span key={i}>{segment.content}</span>;
        }
      })}
    </span>
  );
}
