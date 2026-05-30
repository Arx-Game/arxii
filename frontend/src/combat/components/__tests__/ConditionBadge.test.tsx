/**
 * Tests for ConditionBadge — small chip rendering a single active condition,
 * deep-linking to the shared condition-detail modal on click.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import type { ReactNode } from 'react';

import { ConditionBadge } from '../ConditionBadge';
import { deepLinkModalSlice } from '@/store/deepLinkModalSlice';
import type { components } from '@/generated/api';

type ConditionInstance = components['schemas']['ConditionInstance'];

function makeStore() {
  return configureStore({ reducer: { deepLinkModal: deepLinkModalSlice.reducer } });
}

function Wrapper({
  children,
  store = makeStore(),
}: {
  children: ReactNode;
  store?: ReturnType<typeof makeStore>;
}) {
  return <Provider store={store}>{children}</Provider>;
}

function makeCondition(overrides: Partial<ConditionInstance> = {}): ConditionInstance {
  return {
    id: 7,
    name: 'Bleeding Out',
    icon: '🩸',
    color_hex: '#cc0000',
    display_priority: 10,
    ...overrides,
  } as unknown as ConditionInstance;
}

describe('ConditionBadge', () => {
  it('renders the icon', () => {
    render(
      <Wrapper>
        <ConditionBadge condition={makeCondition()} />
      </Wrapper>
    );

    expect(screen.getByText('🩸')).toBeInTheDocument();
  });

  it('exposes an accessible name / tooltip with the condition name', () => {
    render(
      <Wrapper>
        <ConditionBadge condition={makeCondition()} />
      </Wrapper>
    );

    const button = screen.getByRole('button', { name: /Bleeding Out/i });
    expect(button).toHaveAttribute('title', expect.stringContaining('Bleeding Out'));
  });

  it('dispatches openDeepLink({modal: "condition", id}) on click', async () => {
    const store = makeStore();
    const user = userEvent.setup();

    render(
      <Wrapper store={store}>
        <ConditionBadge condition={makeCondition({ id: 7 })} />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /Bleeding Out/i }));

    expect(store.getState().deepLinkModal.current).toEqual({ modal: 'condition', id: 7 });
  });

  it('applies color_hex via inline style', () => {
    render(
      <Wrapper>
        <ConditionBadge condition={makeCondition({ color_hex: '#00aa00' })} />
      </Wrapper>
    );

    const button = screen.getByRole('button', { name: /Bleeding Out/i });
    // jsdom normalizes hex to rgb in the serialized style string.
    expect(button.style.color).toBe('rgb(0, 170, 0)');
    expect(button.style.borderColor).toBe('rgb(0, 170, 0)');
  });
});
