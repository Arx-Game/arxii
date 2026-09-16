import type { Visibility } from './types';

export const VISIBILITY_LABELS: Record<Visibility, string> = {
  public: 'Public',
  obscure: 'Obscure',
  secret: 'Secret',
};

/** The tier a Codex row sits at, read the way the editor reads a being's. */
export function tierOf(isPublic: boolean, organizations: string[]): Visibility {
  if (isPublic) return 'public';
  return organizations.length > 0 ? 'obscure' : 'secret';
}
