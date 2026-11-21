import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { SwitchableAlternateSelf } from '../../formQueries';
import type { SwitchablePersona } from '../../personaQueries';
import { GuiseSheetDialog } from '../GuiseSheetDialog';

const { portraitMutate } = vi.hoisted(() => ({ portraitMutate: vi.fn() }));

vi.mock('../../faceQueries', () => ({
  useFacePortraitMutation: () => ({ mutate: portraitMutate, isPending: false }),
  useSetFaceDescriptionMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePortraitChoicesQuery: () => ({ data: [], isError: false }),
}));
vi.mock('../../personaQueries', () => ({
  useSetPersonaProfileMutation: () => ({
    mutateAsync: vi.fn(),
    reset: vi.fn(),
    isPending: false,
  }),
}));
vi.mock('@/roster/gallery', () => ({ useMediaUsageQuery: () => ({ data: undefined }) }));

const mask: SwitchablePersona = {
  id: 7,
  name: 'owl mask',
  persona_type: 'temporary',
  is_fake_name: true,
  thumbnail_url: null,
  thumbnail_media_url: null,
  guise_concept: '',
  guise_quote: '',
  guise_never_do: '',
  guise_protect: '',
  guise_fear: '',
  guise_background: '',
  description: 'Slim and straight-backed.',
  has_portrait: true,
};

const hollowForm: SwitchableAlternateSelf = {
  id: 3,
  display_name: 'Hollow Form',
  persona_name: null,
  form_name: null,
  has_combat_profile: false,
  has_techniques: false,
  is_active: false,
  compulsion: null,
  persona_id: null,
  thumbnail_url: '',
  has_portrait: true,
};

// A unit the journeys cannot reach: which face the dialog writes to, and which fields it
// hides for a self with no persona. What a stranger then sees is in the journey file.
describe('GuiseSheetDialog', () => {
  it('shows a mask its portrait controls and its own description', () => {
    portraitMutate.mockClear();
    render(<GuiseSheetDialog persona={mask} characterSheetId={1} open onOpenChange={vi.fn()} />);

    expect(screen.getByText('How this face looks')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toHaveValue('Slim and straight-backed.');
    fireEvent.click(screen.getByRole('button', { name: 'Remove portrait' }));
    expect(portraitMutate).toHaveBeenCalledWith(
      { target: { kind: 'persona', personaId: 7 }, change: { kind: 'clear' } },
      expect.anything()
    );
  });

  it('gives an alternate self with no persona a portrait and no description or bio', () => {
    portraitMutate.mockClear();
    render(
      <GuiseSheetDialog
        persona={null}
        alternateSelf={hollowForm}
        characterSheetId={1}
        open
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.queryByLabelText('Description')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Concept')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save guise sheet' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove portrait' }));
    expect(portraitMutate).toHaveBeenCalledWith(
      { target: { kind: 'alternate', alternateSelfId: 3 }, change: { kind: 'clear' } },
      expect.anything()
    );
  });
});
