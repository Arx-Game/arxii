import { useMemo } from 'react';

interface EvenniaMessageProps {
  content: string;
  className?: string;
}

// Evennia color class mappings to Tailwind classes
const colorMap: Record<string, string> = {
  'color-000': 'text-gray-900', // Black
  'color-001': 'text-red-700', // Dark Red
  'color-002': 'text-green-700', // Dark Green
  'color-003': 'text-yellow-600', // Dark Yellow
  'color-004': 'text-blue-700', // Dark Blue
  'color-005': 'text-purple-700', // Dark Magenta
  'color-006': 'text-cyan-700', // Dark Cyan
  'color-007': 'text-gray-400', // Light Gray
  'color-008': 'text-gray-600', // Dark Gray
  'color-009': 'text-red-400', // Light Red
  'color-010': 'text-green-400', // Light Green
  'color-011': 'text-yellow-400', // Light Yellow
  'color-012': 'text-blue-400', // Light Blue
  'color-013': 'text-purple-400', // Light Magenta
  'color-014': 'text-cyan-400', // Light Cyan
  'color-015': 'text-white', // White
};

export function EvenniaMessage({ content, className = '' }: EvenniaMessageProps) {
  const processedContent = useMemo(() => {
    // Convert Evennia color classes to Tailwind classes
    let processed = content;

    // Replace color classes
    Object.entries(colorMap).forEach(([evenniaClass, tailwindClass]) => {
      const regex = new RegExp(`class="${evenniaClass}"`, 'g');
      processed = processed.replace(regex, `class="${tailwindClass}"`);
    });

    // Convert line breaks
    processed = processed.replace(/<br>/g, '\n');

    return processed;
  }, [content]);

  // For now, we'll render HTML directly but sanitize it later if needed
  // This is safe for Evennia output but would need sanitization for user input
  return (
    <div
      className={`whitespace-pre-wrap font-mono text-sm ${className}`}
      dangerouslySetInnerHTML={{ __html: processedContent }}
    />
  );
}
