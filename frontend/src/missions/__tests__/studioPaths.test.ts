import { describe, expect, it } from 'vitest';

import { studioBaseFromPath, studioPaths } from '../studioPaths';

describe('studioBaseFromPath', () => {
  it('reads "scenario" off a /stories/scenarios/... path', () => {
    expect(studioBaseFromPath('/stories/scenarios/7/canvas')).toBe('scenario');
    expect(studioBaseFromPath('/stories/scenarios/7/nodes/9')).toBe('scenario');
  });

  it('reads "staff" off a /staff/missions/... path', () => {
    expect(studioBaseFromPath('/staff/missions/7/canvas')).toBe('staff');
  });

  it('falls back to "staff" for any other path', () => {
    expect(studioBaseFromPath('/stories/author/3')).toBe('staff');
    expect(studioBaseFromPath('/')).toBe('staff');
  });
});

describe('studioPaths', () => {
  it('builds scenario-base links from the story id', () => {
    const paths = studioPaths('scenario', 7, 3);
    expect(paths.browser).toBe('/stories/author/3');
    expect(paths.browserLabel).toBe('Scenario');
    expect(paths.canvas).toBe('/stories/scenarios/7/canvas');
    expect(paths.node(9)).toBe('/stories/scenarios/7/nodes/9');
    expect(paths.option(9, 12)).toBe('/stories/scenarios/7/nodes/9/options/12');
  });

  it('falls back to the generic author page when no story id is known', () => {
    const paths = studioPaths('scenario', 7, null);
    expect(paths.browser).toBe('/stories/author');
    const paths2 = studioPaths('scenario', 7);
    expect(paths2.browser).toBe('/stories/author');
  });

  it('builds staff-base links unchanged', () => {
    const paths = studioPaths('staff', 7, 3);
    expect(paths.browser).toBe('/staff/missions?id=7');
    expect(paths.browserLabel).toBe('Missions');
    expect(paths.canvas).toBe('/staff/missions/7/canvas');
    expect(paths.node(9)).toBe('/staff/missions/7/nodes/9');
    expect(paths.option(9, 12)).toBe('/staff/missions/7/nodes/9/options/12');
  });
});
