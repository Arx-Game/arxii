import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { LookDialog } from './LookDialog';

function renderDialog(overrides = {}) {
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    personaName: 'Cassia Vell',
    thumbnailUrl: null,
    text: 'A tall woman with ink-stained fingers.',
    isLoading: false,
    onViewSheet: vi.fn(),
    ...overrides,
  };
  render(<LookDialog {...props} />);
  return props;
}

describe('LookDialog', () => {
  it('shows the look text under the persona name', () => {
    renderDialog();
    expect(screen.getByRole('dialog', { name: 'Cassia Vell' })).toBeInTheDocument();
    expect(screen.getByText(/ink-stained fingers/)).toBeInTheDocument();
  });

  it('breaks the look text on its own lines (Status / Wearing / Markings, #4030)', () => {
    renderDialog({ text: 'Status: Healthy\nWearing: A grey cloak\nMarkings: None' });
    // FormattedContent (Task 4030's LookDialog body) wraps every segment's
    // text in its own inner <span>; the whitespace-pre-wrap class lives on
    // FormattedContent's own outer span, one level up.
    const wrapper = screen.getByText(/Status: Healthy/).closest('.whitespace-pre-wrap');
    expect(wrapper).not.toBeNull();
    expect(wrapper).toHaveTextContent(/Wearing: A grey cloak/);
  });

  it('closes on Escape', async () => {
    const props = renderDialog();
    await userEvent.keyboard('{Escape}');
    expect(props.onOpenChange).toHaveBeenCalledWith(false);
  });

  it('opens the sheet from its button', async () => {
    const props = renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'View sheet' }));
    expect(props.onViewSheet).toHaveBeenCalled();
  });

  it('moves when its title bar is dragged', () => {
    renderDialog();
    const handle = screen.getByTestId('look-dialog-handle');
    fireEvent.pointerDown(handle, { clientX: 100, clientY: 100, button: 0 });
    fireEvent.pointerMove(document, { clientX: 160, clientY: 130 });
    fireEvent.pointerUp(document);
    expect(screen.getByRole('dialog').style.transform).toContain('60px');
  });

  it('draws no dark overlay behind it', () => {
    renderDialog();
    expect(document.querySelector('[data-testid="look-dialog-overlay"]')).toBeNull();
  });
});
