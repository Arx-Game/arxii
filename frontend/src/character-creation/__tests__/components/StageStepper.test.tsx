/**
 * StageStepper Component Tests
 *
 * Confirms the stage relabeling from #2426 Task 9 (Path/Gift split out of the
 * old "Path & Skills"/"Magic" stages) is reflected in the stepper labels.
 */

import { render, screen } from '@testing-library/react';
import { StageStepper } from '../../components/StageStepper';
import { Stage } from '../../types';

const ALL_INCOMPLETE = Object.fromEntries(
  Object.values(Stage)
    .filter((value): value is Stage => typeof value === 'number')
    .map((stage) => [stage, false])
) as Record<Stage, boolean>;

describe('StageStepper', () => {
  it('labels stages 5-7 as Path, Gift, and Attributes & Skills', () => {
    render(
      <StageStepper
        currentStage={Stage.PATH}
        stageCompletion={ALL_INCOMPLETE}
        stageErrors={{}}
        onStageSelect={() => {}}
      />
    );

    expect(screen.getByText('Path')).toBeInTheDocument();
    expect(screen.getByText('Gift')).toBeInTheDocument();
    expect(screen.getByText('Attributes & Skills')).toBeInTheDocument();
  });
});
