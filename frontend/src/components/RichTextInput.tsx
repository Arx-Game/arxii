import * as React from 'react';

import { cn } from '@/lib/utils';

import { ColorPicker } from './ColorPicker';
import { NameAutocomplete } from './NameAutocomplete';

interface AutocompleteState {
  visible: boolean;
  query: string;
  startPos: number;
  selectedIndex: number;
}

interface RichTextInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  rows?: number;
  className?: string;
  leftSlot?: React.ReactNode;
  rightSlot?: React.ReactNode;
  ghostText?: string;
  autocompleteItems?: Array<{ name: string; thumbnail_url?: string | null }>;
}

function detectMention(
  text: string,
  cursorPos: number
): { startPos: number; query: string } | null {
  let i = cursorPos - 1;
  while (i >= 0 && text[i] !== '@' && text[i] !== ' ' && text[i] !== '\n') {
    i--;
  }
  if (
    i >= 0 &&
    text[i] === '@' &&
    (i === 0 || text[i - 1] === ' ' || text[i - 1] === '\n' || text[i - 1] === ',')
  ) {
    const query = text.substring(i + 1, cursorPos);
    return { startPos: i, query };
  }
  return null;
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
  rows = 3,
  className,
  leftSlot,
  rightSlot,
  ghostText,
  autocompleteItems,
}: RichTextInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const [autocompleteState, setAutocompleteState] = React.useState<AutocompleteState | null>(null);

  const filteredItems = React.useMemo(() => {
    if (!autocompleteState?.visible || !autocompleteItems) return [];
    return autocompleteItems.filter((c) =>
      c.name.toLowerCase().startsWith(autocompleteState.query.toLowerCase())
    );
  }, [autocompleteState?.visible, autocompleteState?.query, autocompleteItems]);

  const handleWrap = React.useCallback(
    (before: string, after: string) => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      wrapSelection(textarea, before, after, value, onChange);
    },
    [value, onChange]
  );

  const handleAutocompleteSelect = React.useCallback(
    (name: string) => {
      if (!autocompleteState) return;
      const before = value.slice(0, autocompleteState.startPos);
      const after = value.slice(autocompleteState.startPos + 1 + autocompleteState.query.length);
      const newValue = before + '@' + name + after;
      onChange(newValue);
      setAutocompleteState(null);

      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (textarea) {
          const cursorPos = autocompleteState.startPos + 1 + name.length;
          textarea.focus();
          textarea.selectionStart = cursorPos;
          textarea.selectionEnd = cursorPos;
        }
      });
    },
    [autocompleteState, value, onChange]
  );

  const handleKeyDown = React.useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Handle autocomplete navigation first
      if (autocompleteState?.visible && filteredItems.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setAutocompleteState((prev) =>
            prev
              ? {
                  ...prev,
                  selectedIndex: (prev.selectedIndex + 1) % filteredItems.length,
                }
              : null
          );
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setAutocompleteState((prev) =>
            prev
              ? {
                  ...prev,
                  selectedIndex:
                    (prev.selectedIndex - 1 + filteredItems.length) % filteredItems.length,
                }
              : null
          );
          return;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault();
          const selected = filteredItems[autocompleteState.selectedIndex];
          if (selected) {
            handleAutocompleteSelect(selected.name);
          }
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setAutocompleteState(null);
          return;
        }
      }

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
    [autocompleteState, filteredItems, handleAutocompleteSelect, handleWrap, onSubmit, onKeyDown]
  );

  const handleChange = React.useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value;
      onChange(newValue);

      if (autocompleteItems && autocompleteItems.length > 0) {
        const cursorPos = e.target.selectionStart;
        const mention = detectMention(newValue, cursorPos);
        if (mention) {
          setAutocompleteState({
            visible: true,
            query: mention.query,
            startPos: mention.startPos,
            selectedIndex: 0,
          });
        } else {
          setAutocompleteState(null);
        }
      }
    },
    [onChange, autocompleteItems]
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
        {leftSlot}
        <button
          type="button"
          title="Bold (Ctrl+B)"
          aria-label="Bold"
          className="flex h-6 w-6 items-center justify-center rounded text-xs font-bold hover:bg-accent hover:text-accent-foreground"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => handleWrap('**', '**')}
        >
          B
        </button>
        <button
          type="button"
          title="Italic (Ctrl+I)"
          aria-label="Italic"
          className="flex h-6 w-6 items-center justify-center rounded text-xs italic hover:bg-accent hover:text-accent-foreground"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => handleWrap('*', '*')}
        >
          I
        </button>
        <button
          type="button"
          title="Strikethrough (Ctrl+Shift+S)"
          aria-label="Strikethrough"
          className="flex h-6 w-6 items-center justify-center rounded text-xs line-through hover:bg-accent hover:text-accent-foreground"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => handleWrap('~~', '~~')}
        >
          S
        </button>
        <div className="mx-1 h-4 w-px bg-border" />
        <ColorPicker onSelectColor={handleColorSelect} />
        {rightSlot}
      </div>

      {/* Textarea with ghost text and autocomplete */}
      <div className="relative">
        {!value && ghostText && (
          <div className="pointer-events-none absolute inset-0 px-3 py-2 text-sm text-muted-foreground/40">
            {ghostText}
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={rows}
          spellCheck={true}
          className="relative w-full resize-none bg-transparent px-3 py-2 text-base focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm"
        />
        {autocompleteItems && (
          <NameAutocomplete
            characters={autocompleteItems}
            query={autocompleteState?.query ?? ''}
            visible={autocompleteState?.visible ?? false}
            onSelect={handleAutocompleteSelect}
            onDismiss={() => setAutocompleteState(null)}
            selectedIndex={autocompleteState?.selectedIndex ?? 0}
          />
        )}
      </div>
    </div>
  );
}
