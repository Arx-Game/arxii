import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ArtDialog } from '../ArtDialog';

const mockFetchPlayerMedia = vi.fn();
const mockUploadPlayerMedia = vi.fn();
vi.mock('@/roster/api', () => ({
  fetchPlayerMedia: () => mockFetchPlayerMedia(),
  uploadPlayerMedia: (form: FormData) => mockUploadPlayerMedia(form),
}));

const libraryPiece = {
  id: 7,
  cloudinary_public_id: 'x',
  cloudinary_url: 'https://img.example/hart.png',
  media_type: 'photo',
  title: 'The Golden Hart',
  description: '',
  created_by: null,
  uploaded_date: '2026-08-01T00:00:00Z',
  updated_date: '2026-08-01T00:00:00Z',
};

function renderDialog(overrides: Partial<Parameters<typeof ArtDialog>[0]> = {}) {
  const onHang = vi.fn();
  const onTakeDown = vi.fn();
  const onOpenChange = vi.fn();
  renderWithProviders(
    <ArtDialog
      open
      onOpenChange={onOpenChange}
      subjectName="The Grand Foyer"
      currentArtUrl={null}
      onHang={onHang}
      onTakeDown={onTakeDown}
      {...overrides}
    />
  );
  return { onHang, onTakeDown, onOpenChange };
}

describe('ArtDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPlayerMedia.mockResolvedValue([libraryPiece]);
  });

  it('hangs a library piece and closes', async () => {
    const { onHang, onOpenChange } = renderDialog();
    await userEvent.click(await screen.findByTestId('art-option-7'));
    expect(onHang).toHaveBeenCalledWith(7);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('take-down shows only with current art and fires onTakeDown', async () => {
    const { onTakeDown } = renderDialog({ currentArtUrl: 'https://img.example/old.png' });
    await userEvent.click(screen.getByTestId('art-take-down'));
    expect(onTakeDown).toHaveBeenCalled();
  });

  it('an upload hangs the fresh piece immediately', async () => {
    mockUploadPlayerMedia.mockResolvedValue({ ...libraryPiece, id: 9 });
    const { onHang } = renderDialog();

    const input = screen.getByTestId('art-upload-input');
    await userEvent.upload(input, new File(['x'], 'ward.png', { type: 'image/png' }));

    expect(mockUploadPlayerMedia).toHaveBeenCalled();
    expect(onHang).toHaveBeenCalledWith(9);
  });
});
