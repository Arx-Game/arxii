import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { store } from '@/store/store';
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <Provider store={store}>
      <QueryClientProvider client={client}>
        <LookDialog {...props} />
      </QueryClientProvider>
    </Provider>
  );
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

  it('renders only server-returned visible worn rows alongside the Look result', () => {
    renderDialog({
      partition: 'account-1',
      actorId: 42,
      visibleWornItems: [
        {
          id: 81,
          display_name: 'A copper gorget',
          body_region: 'neck',
          equipment_layer: 'outer',
          owner_persona_id: 19,
        },
      ],
    });
    expect(screen.getByRole('region', { name: 'Visible worn items' })).toHaveTextContent(
      'A copper gorget'
    );
    expect(screen.getByRole('button', { name: /A copper gorget/ })).toBeInTheDocument();
    expect(screen.queryByText('private inventory')).not.toBeInTheDocument();
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
