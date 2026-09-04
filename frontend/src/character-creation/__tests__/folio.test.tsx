import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import {
  ChapterLeaf,
  Entry,
  EntryDoors,
  EntryList,
  InstrumentFrame,
  InstrumentGroup,
  RecordRail,
  StatRow,
} from '../folio';
import { Stage } from '../types';

describe('ChapterLeaf', () => {
  it('opens with the eyebrow and one h1 and puts the aside in a marginalia landmark', () => {
    render(
      <ChapterLeaf stage={Stage.ORIGIN} title="Where does the story begin?" aside={<p>note</p>}>
        <p>body</p>
      </ChapterLeaf>
    );
    expect(screen.getByText('Chapter the First')).toHaveClass('chapter-no');
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('complementary', { name: /marginalia/i })).toHaveTextContent('note');
  });
});

describe('RecordRail', () => {
  it('lists chosen values and marks the unchosen as unwritten', () => {
    render(
      <RecordRail
        rows={[{ label: 'Origin', value: 'Perdition' }, { label: 'Species' }]}
        ledger="One of eleven chapters begun."
      />
    );
    expect(screen.getByRole('heading', { name: /the record, so far/i })).toBeInTheDocument();
    expect(screen.getByText('Perdition')).toBeInTheDocument();
    expect(screen.getByText('not yet chosen')).toHaveClass('unwritten');
    expect(screen.getByText('One of eleven chapters begun.')).toHaveClass('rail-ledger');
  });
});

describe('Entry', () => {
  it('keeps every control out of the summary and reports the chosen state on the door', async () => {
    const onChoose = vi.fn();
    render(
      <EntryList label="Starting realms">
        <Entry name="Perdition" tag="The Grand Principality of Inferna" chosen={false}>
          <p>prose</p>
          <EntryDoors
            chooseLabel="Begin in Perdition"
            onChoose={onChoose}
            chosen={false}
            onSetAside={vi.fn()}
          />
        </Entry>
      </EntryList>
    );
    const summary = screen.getByText('Perdition').closest('summary')!;
    expect(summary.querySelectorAll('button, a')).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: /begin in perdition/i }));
    expect(onChoose).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /begin in perdition/i })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
  });
});

describe('StatRow', () => {
  it('labels the output, disables at the cap with a reason, and announces nothing itself', () => {
    render(
      <InstrumentFrame
        label="Statistics"
        ledger={{
          left: 'Twelve statistics',
          right: (
            <>
              Points remaining: <b>0</b>
            </>
          ),
        }}
      >
        <InstrumentGroup title="Physical" gloss="the body">
          <StatRow
            id="lbl-strength"
            name="strength"
            value={6}
            max={6}
            onChange={vi.fn()}
            canDecrease
            canIncrease={false}
            increaseTitle="At 6, the most it can be"
          />
        </InstrumentGroup>
      </InstrumentFrame>
    );
    expect(screen.getByRole('status', { hidden: true })).toHaveTextContent('6');
    const plus = screen.getByRole('button', { name: /raise strength/i });
    expect(plus).toBeDisabled();
    expect(plus).toHaveAttribute('title', 'At 6, the most it can be');
  });
});
