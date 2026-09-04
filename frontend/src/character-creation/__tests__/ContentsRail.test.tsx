import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ContentsRail } from '../folio/ContentsRail';
import { Stage } from '../types';

const completion = (done: Stage[]): Record<Stage, boolean> =>
  Object.fromEntries(
    Object.values(Stage)
      .filter((v): v is Stage => typeof v === 'number')
      .map((s) => [s, done.includes(s)])
  ) as Record<Stage, boolean>;

describe('ContentsRail', () => {
  it('lists the eleven chapters with Arabic numerals and marks the current one', () => {
    render(
      <ContentsRail
        currentStage={Stage.ATTRIBUTES}
        stageCompletion={completion([Stage.ORIGIN, Stage.HERITAGE])}
        stageErrors={{}}
        onStageSelect={vi.fn()}
      />
    );
    const nav = screen.getByRole('navigation', { name: /chapters of your character/i });
    expect(nav.querySelectorAll('li')).toHaveLength(11);
    expect(screen.getByText('7')).toBeInTheDocument();
    const current = screen.getByRole('link', { current: 'step' });
    expect(current).toHaveTextContent('Attributes');
    expect(screen.getByText('Origin').closest('li')).toHaveClass('toc-done');
  });

  it('renders a validation reason as an n.b. note on an incomplete chapter', () => {
    render(
      <ContentsRail
        currentStage={Stage.REVIEW}
        stageCompletion={completion([Stage.ORIGIN])}
        stageErrors={{ [Stage.FINAL_TOUCHES]: ['No goal set down.'] }}
        onStageSelect={vi.fn()}
      />
    );
    expect(screen.getByText('No goal set down.')).toBeInTheDocument();
  });

  it('navigates when a chapter is chosen', async () => {
    const onSelect = vi.fn();
    render(
      <ContentsRail
        currentStage={Stage.ORIGIN}
        stageCompletion={completion([])}
        stageErrors={{}}
        onStageSelect={onSelect}
      />
    );
    await userEvent.click(screen.getByRole('link', { name: /heritage/i }));
    expect(onSelect).toHaveBeenCalledWith(Stage.HERITAGE);
  });
});
