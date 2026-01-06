import { screen } from '@testing-library/react';
import { SceneListCard } from './SceneListCard';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { SceneSummary } from '@/scenes/types';

describe('SceneListCard', () => {
  it('renders title and empty message when no scenes', () => {
    renderWithProviders(
      <SceneListCard title="Test Scenes" scenes={[]} emptyMessage="No scenes available." />
    );

    expect(screen.getByText('Test Scenes')).toBeInTheDocument();
    expect(screen.getByText('No scenes available.')).toBeInTheDocument();
  });

  it('renders scenes with valid participants', () => {
    const scenes: SceneSummary[] = [
      {
        id: 1,
        name: 'Adventure Scene',
        participants: [
          {
            id: 101,
            name: 'Hero',
            roster_entry: { id: 201, name: 'Alice', profile_url: 'https://example.com/alice.jpg' },
          },
          {
            id: 102,
            name: 'Villain',
            roster_entry: { id: 202, name: 'Bob' },
          },
        ],
      },
    ];

    renderWithProviders(
      <SceneListCard title="Active Scenes" scenes={scenes} emptyMessage="No active scenes." />
    );

    expect(screen.getByText('Active Scenes')).toBeInTheDocument();
    expect(screen.getByText('Adventure Scene')).toBeInTheDocument();
    // Avatar fallbacks should be rendered
    expect(screen.getByText('A')).toBeInTheDocument();
    expect(screen.getByText('B')).toBeInTheDocument();
  });

  it('handles participants with null roster_entry gracefully', () => {
    // This is the key test - participants without roster_entry should not crash the component
    const scenes: SceneSummary[] = [
      {
        id: 1,
        name: 'Scene with Mixed Participants',
        participants: [
          {
            id: 101,
            name: 'Valid Character',
            roster_entry: { id: 201, name: 'Alice' },
          },
          {
            id: 102,
            name: 'NPC without roster',
            roster_entry: null as unknown as { id: number; name: string },
          },
          {
            id: 103,
            name: 'Another NPC',
            roster_entry: undefined as unknown as { id: number; name: string },
          },
        ],
      },
    ];

    // Should not throw an error
    renderWithProviders(
      <SceneListCard title="Mixed Scenes" scenes={scenes} emptyMessage="No scenes." />
    );

    expect(screen.getByText('Mixed Scenes')).toBeInTheDocument();
    expect(screen.getByText('Scene with Mixed Participants')).toBeInTheDocument();
    // Only Alice should be rendered (the valid participant)
    expect(screen.getByText('A')).toBeInTheDocument();
    // Should not show any fallback for null/undefined roster_entry participants
  });

  it('handles scenes where all participants have null roster_entry', () => {
    const scenes: SceneSummary[] = [
      {
        id: 1,
        name: 'NPC Only Scene',
        participants: [
          {
            id: 101,
            name: 'NPC 1',
            roster_entry: null as unknown as { id: number; name: string },
          },
          {
            id: 102,
            name: 'NPC 2',
            roster_entry: null as unknown as { id: number; name: string },
          },
        ],
      },
    ];

    renderWithProviders(
      <SceneListCard title="NPC Scenes" scenes={scenes} emptyMessage="No scenes." />
    );

    expect(screen.getByText('NPC Scenes')).toBeInTheDocument();
    expect(screen.getByText('NPC Only Scene')).toBeInTheDocument();
    // No avatars should be rendered since all participants lack roster_entry
  });

  it('handles empty participants array', () => {
    const scenes: SceneSummary[] = [
      {
        id: 1,
        name: 'Empty Scene',
        participants: [],
      },
    ];

    renderWithProviders(<SceneListCard title="Scenes" scenes={scenes} emptyMessage="No scenes." />);

    expect(screen.getByText('Scenes')).toBeInTheDocument();
    expect(screen.getByText('Empty Scene')).toBeInTheDocument();
  });

  it('renders multiple scenes correctly', () => {
    const scenes: SceneSummary[] = [
      {
        id: 1,
        name: 'First Scene',
        participants: [{ id: 101, name: 'Char1', roster_entry: { id: 201, name: 'Player1' } }],
      },
      {
        id: 2,
        name: 'Second Scene',
        participants: [{ id: 102, name: 'Char2', roster_entry: { id: 202, name: 'Player2' } }],
      },
    ];

    renderWithProviders(
      <SceneListCard title="All Scenes" scenes={scenes} emptyMessage="No scenes." />
    );

    expect(screen.getByText('All Scenes')).toBeInTheDocument();
    expect(screen.getByText('First Scene')).toBeInTheDocument();
    expect(screen.getByText('Second Scene')).toBeInTheDocument();
  });
});
