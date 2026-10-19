/** The first letters of the first two words ("Captain Vael" -> "CV"); "?" for an empty name. */
export function initials(name: string): string {
  const letters = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '');
  return letters.join('') || '?';
}
