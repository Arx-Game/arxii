/**
 * Knowledge (#5206, owner ruling 2026-11-26): the owner's Secrets column lists the
 * character's own secrets from the sheet payload, the ones it knows about itself. The
 * server carries them for the owner and staff only; drawing what we are handed is the gate.
 */
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import type { CharacterSheetOwnSecret } from '@/character_sheets/api';
import { KnowledgePanel } from '../panels';

vi.mock('@/clues/components/CluesTab', () => ({ CluesTab: () => null }));
vi.mock('@/secrets/components/GossipPanel', () => ({ GossipPanel: () => null }));
vi.mock('@/secrets/components/StaffSecretsPanel', () => ({ StaffSecretsPanel: () => null }));

function ownSecret(overrides: Partial<CharacterSheetOwnSecret>): CharacterSheetOwnSecret {
  return {
    id: 1,
    level: 'Carefully Kept',
    content: 'Hidden Shame',
    provenance: 'GM-authored',
    found_at: null,
    can_grieve: false,
    subject: 'Ione Fatui',
    category: 'Unknown',
    consequences: 'Unknown',
    author: 'GM/Staff',
    anchored_to: [],
    ...overrides,
  };
}

function renderPanel(ownSecrets: CharacterSheetOwnSecret[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <KnowledgePanel sheetId={7} viewerEntryId={3} isStaff={false} ownSecrets={ownSecrets} />
    </QueryClientProvider>
  );
}

describe('KnowledgePanel', () => {
  it("lists the character's own secrets for its player", () => {
    renderPanel([
      ownSecret({ id: 11, content: 'Hidden Shame' }),
      ownSecret({
        id: 12,
        level: 'Uncommon Knowledge',
        content: 'Ione once sank a ship.',
        provenance: 'Player flavor',
        author: 'Ione Fatui',
      }),
    ]);

    expect(screen.getByText('Hidden Shame')).toBeInTheDocument();
    expect(screen.getByText('Ione once sank a ship.')).toBeInTheDocument();
  });

  it('says so when the character keeps none', () => {
    renderPanel([]);

    expect(screen.getByText('You know nothing of theirs.')).toBeInTheDocument();
  });
});
