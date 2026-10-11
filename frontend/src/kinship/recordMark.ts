/** The mark the record carries after a name (#4239): (RIP), (Missing), or nothing. */
export function recordMark(node: { is_deceased: boolean; is_missing?: boolean }): string {
  if (node.is_deceased) return ' (RIP)';
  if (node.is_missing) return ' (Missing)';
  return '';
}
