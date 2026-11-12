/**
 * The thin "N hidden" rule shown in place of a run of hidden lines. Scenes wrap
 * it in a button that expands muted poses (#2087); channels show it as-is for
 * blocked authors and it never expands (#3299).
 */
export function HiddenDivider({
  label,
  onClick,
  disabled,
  testId = 'hidden-divider',
}: {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  testId?: string;
}) {
  const className = 'my-1 flex w-full items-center gap-2 px-4 py-1 text-xs text-muted-foreground';
  const content = (
    <>
      <span className="h-px flex-1 bg-border" />
      <span>{label}</span>
      <span className="h-px flex-1 bg-border" />
    </>
  );
  if (!onClick) {
    return (
      <div className={className} data-testid={testId}>
        {content}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`${className} hover:text-foreground`}
      data-testid={testId}
    >
      {content}
    </button>
  );
}
