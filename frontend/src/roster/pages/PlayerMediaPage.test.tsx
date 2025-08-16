import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '../../test/utils/renderWithProviders';
import { PlayerMediaPage } from './PlayerMediaPage';
import type { UseQueryResult } from '@tanstack/react-query';
import type { PlayerMedia } from '../types';

vi.mock('../queries', () => ({
  usePlayerMediaQuery: vi.fn(),
}));
import { usePlayerMediaQuery } from '../queries';

vi.mock('../components/MediaUploadForm', () => ({
  MediaUploadForm: () => <div>Upload</div>,
}));
vi.mock('../components/GalleryManagement', () => ({
  GalleryManagement: () => <div>Gallery</div>,
}));

const mockUsePlayerMediaQuery = vi.mocked(usePlayerMediaQuery);

describe('PlayerMediaPage', () => {
  it('renders list of media', () => {
    mockUsePlayerMediaQuery.mockReturnValue({
      data: [
        {
          id: 1,
          cloudinary_public_id: 'abc',
          cloudinary_url: '',
          media_type: 'image',
          title: 'Test Media',
          description: '',
          created_by: null,
          uploaded_date: '',
          updated_date: '',
        },
      ],
      refetch: vi.fn(),
      isLoading: false,
      isError: false,
      error: null,
      isPending: false,
      isSuccess: true,
    } as unknown as UseQueryResult<PlayerMedia[], Error>);
    renderWithProviders(<PlayerMediaPage />);
    expect(screen.getByText('My Media')).toBeInTheDocument();
    expect(screen.getByText('Test Media')).toBeInTheDocument();
  });
});
