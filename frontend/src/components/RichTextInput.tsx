import * as React from 'react';

import { cn } from '@/lib/utils';

import { ColorPicker } from './ColorPicker';

interface RichTextInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  rows?: number;
  className?: string;
}

function wrapSelection(
  textarea: HTMLTextAreaElement,
  before: string,
  after: string,
  value: string,
  onChange: (value: string) => void
) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = value.slice(start, end);

  const newValue = value.slice(0, start) + before + selected + after + value.slice(end);
  onChange(newValue);

  // Position cursor after the wrapping operation
  requestAnimationFrame(() => {
    textarea.focus();
    if (selected.length > 0) {
      // Select the wrapped text (after the before marker)
      textarea.selectionStart = start + before.length;
      textarea.selectionEnd = start + before.length + selected.length;
    } else {
      // Place cursor between markers
      const cursorPos = start + before.length;
      textarea.selectionStart = cursorPos;
      textarea.selectionEnd = cursorPos;
    }
  });
}

export function RichTextInput({
  value,
  onChange,
  onSubmit,
  onKeyDown,
  placeholder,
  rows = 3,
  className,
}: RichTextInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  const handleWrap = React.useCallback(
    (before: string, after: string) => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      wrapSelection(textarea, before, after, value, onChange);
    },
    [value, onChange]
  );

  const handleKeyDown = React.useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Keyboard shortcuts for formatting
      if (e.ctrlKey || e.metaKey) {
        if (e.key === 'b') {
          e.preventDefault();
          handleWrap('**', '**');
          return;
        }
        if (e.key === 'i') {
          e.preventDefault();
          handleWrap('*', '*');
          return;
        }
        if (e.shiftKey && (e.key === 'S' || e.key === 's')) {
          e.preventDefault();
          handleWrap('~~', '~~');
          return;
        }
      }

      // Enter to submit, Shift+Enter for newline
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        onSubmit();
        return;
      }

      // Pass through to parent handler
      onKeyDown?.(e);
    },
    [handleWrap, onSubmit, onKeyDown]
  );

  const handleColorSelect = React.useCallback(
    (xtermIndex: number) => {
      handleWrap(`|[${xtermIndex}]`, '|n');
    },
    [handleWrap]
  );

  return (
    <div className={cn('overflow-hidden rounded-md border border-input shadow-sm', className)}>
      {/* Toolbar */}
      <div
        className="flex items-center gap-0.5 border-b border-input bg-muted/50 px-1.5 py-1"
        role="toolbar"
        aria-label="Formatting toolbar"
      >
        <button
          type="button"
          title="Bold (Ctrl+B)"
          className="flex h-6 w-6 items-center justify-center rounded text-xs font-bold hover:bg-accent hover:text-accent-foreground"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => handleWrap('**', '**')}
        >
          B
        </button>
        <button
          type="button"
          title="Italic (Ctrl+I)"
          className="flex h-6 w-6 items-center justify-center rounded text-xs italic hover:bg-accent hover:text-accent-foreground"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => handleWrap('*', '*')}
        >
          I
        </button>
        <button
          type="button"
          title="Strikethrough (Ctrl+Shift+S)"
          className="flex h-6 w-6 items-center justify-center rounded text-xs line-through hover:bg-accent hover:text-accent-foreground"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => handleWrap('~~', '~~')}
        >
          S
        </button>
        <div className="mx-1 h-4 w-px bg-border" />
        <ColorPicker onSelectColor={handleColorSelect} />
      </div>

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={rows}
        spellCheck={true}
        className="w-full resize-none bg-transparent px-3 py-2 text-base placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm"
      />
    </div>
  );
}
