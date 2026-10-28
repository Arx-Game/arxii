/** Unselected pills are outlined; the chosen one is filled in the theme's primary pair. */
export function pillClass(selected: boolean): string {
  return `rounded-full border px-3 py-1 text-sm transition-colors ${
    selected
      ? 'border-primary bg-primary font-semibold text-primary-foreground'
      : 'border-input bg-transparent text-foreground hover:bg-accent hover:text-accent-foreground'
  }`;
}
