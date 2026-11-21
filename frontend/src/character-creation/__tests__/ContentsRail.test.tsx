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

const OPTIONAL = [Stage.IDENTITY, Stage.FINAL_TOUCHES];

function renderRail(props: Partial<Parameters<typeof ContentsRail>[0]> = {}) {
  return render(
    <ContentsRail
      currentStage={Stage.ORIGIN}
      stageCompletion={completion([])}
      stageErrors={{}}
      visitedStages={[]}
      optionalStages={OPTIONAL}
      onStageSelect={vi.fn()}
      {...props}
    />
  );
}

const row = (label: string) => screen.getByText(label).closest('li')!;

describe('ContentsRail', () => {
  it('lists the ten chapters with Arabic numerals and marks the current one', () => {
    renderRail({
      currentStage: Stage.ATTRIBUTES,
      stageCompletion: completion([Stage.ORIGIN, Stage.HERITAGE]),
    });
    const nav = screen.getByRole('navigation', { name: /character creation stages/i });
    expect(nav.querySelectorAll('li')).toHaveLength(10);
    expect(screen.getByText('6')).toBeInTheDocument();
    const current = screen.getByRole('link', { current: 'step' });
    expect(current).toHaveTextContent('Attributes');
    expect(row('Origin')).toHaveClass('toc-done');
  });

  it('renders a validation reason after a hyphen, in plain text, on an opened chapter (#4022)', () => {
    renderRail({
      currentStage: Stage.REVIEW,
      stageCompletion: completion([Stage.ORIGIN]),
      stageErrors: { [Stage.APPEARANCE]: ['Pick a birthday.'] },
      visitedStages: [Stage.APPEARANCE],
    });
    const note = screen.getByText(/Pick a birthday\./).closest('.toc-note')!;
    expect(note).toHaveTextContent(/^- Pick a birthday\.$/);
    expect(note.querySelector('.nb')).toBeNull();
    expect(screen.queryByText('n.b.')).not.toBeInTheDocument();
  });

  it('navigates when a chapter is chosen', async () => {
    const onSelect = vi.fn();
    renderRail({ onStageSelect: onSelect });
    await userEvent.click(screen.getByRole('link', { name: /heritage/i }));
    expect(onSelect).toHaveBeenCalledWith(Stage.HERITAGE);
  });

  // #5199, owner rulings 2026-11-18.
  describe('what a row says about its stage', () => {
    const errors = {
      [Stage.HERITAGE]: ['Select a beginning'],
      [Stage.ATTRIBUTES]: ['Set your statistics'],
    };

    it('shows a stage that has not been opened by its name alone', () => {
      renderRail({ stageErrors: errors, visitedStages: [Stage.ORIGIN] });
      expect(row('Heritage').querySelector('.toc-note')).toBeNull();
      expect(row('Attributes & Skills').querySelector('.toc-note')).toBeNull();
      expect(screen.queryByText(/Select a beginning/)).not.toBeInTheDocument();
      expect(row('Heritage')).toHaveTextContent('not yet opened');
    });

    it('shows what an opened stage still asks', () => {
      renderRail({ stageErrors: errors, visitedStages: [Stage.ORIGIN, Stage.HERITAGE] });
      expect(row('Heritage').querySelector('.toc-note')).toHaveTextContent(
        /^- Select a beginning$/
      );
      // The one beside it, not opened, still says nothing.
      expect(row('Attributes & Skills').querySelector('.toc-note')).toBeNull();
    });

    it('shows what the stage the draft stands on asks, with no visit recorded yet', () => {
      renderRail({ currentStage: Stage.HERITAGE, stageErrors: errors, visitedStages: [] });
      expect(row('Heritage').querySelector('.toc-note')).toHaveTextContent(
        /^- Select a beginning$/
      );
    });

    it('marks a finished stage complete and drops its note', () => {
      renderRail({
        stageCompletion: completion([Stage.HERITAGE]),
        visitedStages: [Stage.ORIGIN, Stage.HERITAGE],
      });
      expect(row('Heritage')).toHaveClass('toc-done');
      expect(row('Heritage')).toHaveTextContent('complete');
      expect(row('Heritage').querySelector('.toc-note')).toBeNull();
    });

    it('reads "optional", never complete, for a stage that asks nothing', () => {
      // The server reports no error for either, so both are "complete" in its terms.
      renderRail({ stageCompletion: completion([Stage.IDENTITY, Stage.FINAL_TOUCHES]) });
      for (const label of ['Identity', 'Final Touches']) {
        expect(row(label)).not.toHaveClass('toc-done');
        expect(row(label).querySelector('.toc-note')).toHaveTextContent(/^optional$/);
        expect(row(label)).not.toHaveTextContent('complete');
        expect(row(label).querySelector('.toc-mark')).toHaveTextContent('');
      }
    });

    it('still reads "optional" once the optional stage has been opened', () => {
      renderRail({
        stageCompletion: completion([Stage.IDENTITY]),
        visitedStages: [Stage.ORIGIN, Stage.IDENTITY],
      });
      expect(row('Identity').querySelector('.toc-note')).toHaveTextContent(/^optional$/);
    });

    it('shows an optional stage its error once it has been opened', () => {
      const over = { [Stage.FINAL_TOUCHES]: ['CG points over budget by 5'] };
      renderRail({ stageErrors: over, visitedStages: [Stage.ORIGIN] });
      expect(row('Final Touches').querySelector('.toc-note')).toHaveTextContent(/^optional$/);
    });

    it('replaces "optional" with the error on an opened optional stage', () => {
      const over = { [Stage.FINAL_TOUCHES]: ['CG points over budget by 5'] };
      renderRail({ stageErrors: over, visitedStages: [Stage.ORIGIN, Stage.FINAL_TOUCHES] });
      expect(row('Final Touches').querySelector('.toc-note')).toHaveTextContent(
        /^- CG points over budget by 5$/
      );
    });
  });
});
