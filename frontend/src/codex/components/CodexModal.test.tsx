import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { CodexModal } from './CodexModal';
import * as queries from '../queries';

vi.mock('../queries');

describe('CodexModal', () => {
  it('renders the entry art when art_url is present', () => {
    vi.mocked(queries.useCodexEntry).mockReturnValue({
      data: {
        id: 1,
        name: 'The Shroud',
        summary: 'A veil between worlds.',
        is_public: true,
        subject: 1,
        subject_name: 'Test Subject',
        subject_path: [],
        display_order: 0,
        knowledge_status: 'known',
        lore_content: null,
        mechanics_content: null,
        lore_links: [],
        mechanics_links: [],
        learn_threshold: 0,
        research_progress: null,
        art_url: 'https://example.com/shroud.jpg',
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof queries.useCodexEntry>);

    renderWithProviders(<CodexModal entryId={1} open onOpenChange={() => {}} />);

    const img = screen.getByRole('img', { name: /The Shroud/i });
    expect(img).toHaveAttribute('src', 'https://example.com/shroud.jpg');
  });

  it('renders nothing extra when art_url is null', () => {
    vi.mocked(queries.useCodexEntry).mockReturnValue({
      data: {
        id: 2,
        name: 'The Flickering',
        summary: 'Something dim.',
        is_public: true,
        subject: 1,
        subject_name: 'Test Subject',
        subject_path: [],
        display_order: 0,
        knowledge_status: 'known',
        lore_content: null,
        mechanics_content: null,
        lore_links: [],
        mechanics_links: [],
        learn_threshold: 0,
        research_progress: null,
        art_url: null,
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof queries.useCodexEntry>);

    renderWithProviders(<CodexModal entryId={2} open onOpenChange={() => {}} />);

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});
