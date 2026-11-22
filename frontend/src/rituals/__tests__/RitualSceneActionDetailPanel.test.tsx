/**
 * RitualSceneActionDetailPanel tests
 *
 * The edit control is offered when the server says the viewer plays a character who knows the
 * ritual (`viewer_can_edit`), never by comparing the viewer's account id to an author (#5280).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RitualSceneActionDetailPanel } from '../components/RitualSceneActionDetailPanel';
import type { RitualWithSchema } from '../types';

vi.mock('@/magic/components/AnimaRitualEditDialog', () => ({
  AnimaRitualEditDialog: () => null,
}));

function ritual(viewerCanEdit: boolean): RitualWithSchema {
  return {
    id: 2,
    name: 'My Anima Ritual',
    description: 'A personal recovery rite.',
    narrative_prose: 'Breath in, breath out.',
    execution_kind: 'SCENE_ACTION',
    input_schema: null,
    author_account_id: 99,
    viewer_can_edit: viewerCanEdit,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;
}

describe('RitualSceneActionDetailPanel', () => {
  it('offers the edit control when the viewer plays a character who knows the ritual', () => {
    render(<RitualSceneActionDetailPanel ritual={ritual(true)} characterSheetId={7} />);
    expect(screen.getByTestId('ritual-edit-button')).toBeInTheDocument();
  });

  it('hides the edit control when the viewer plays no character who knows the ritual', () => {
    render(<RitualSceneActionDetailPanel ritual={ritual(false)} characterSheetId={7} />);
    expect(screen.queryByTestId('ritual-edit-button')).not.toBeInTheDocument();
  });
});
