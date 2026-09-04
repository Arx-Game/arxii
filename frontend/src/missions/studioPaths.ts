/**
 * studioPaths - link builder shared by the two Mission Studio mounts.
 *
 * The editor pages (MissionCanvasPage/NodePage/OptionPage) are mounted
 * twice: under `/staff/missions/...` behind StaffRoute (the original
 * staff-only Mission Studio) and under `/stories/scenarios/...` behind
 * GMRoute (#3565 - lets a GM reach and author the scenario graph behind
 * their own story). Both mounts render the same page components, so
 * every link the pages build has to know which base it is currently
 * under - `studioBaseFromPath` reads that off the current URL and
 * `studioPaths` turns it into the concrete set of links for one
 * template.
 */

export type StudioBase = 'staff' | 'scenario';

/** Which Studio mount a page is running under, from `useLocation().pathname`. */
export function studioBaseFromPath(pathname: string): StudioBase {
  return pathname.startsWith('/stories/scenarios') ? 'scenario' : 'staff';
}

export interface StudioPaths {
  /** Link back to the template's home - the staff browser or the story's author page. */
  browser: string;
  /** Label for that link/breadcrumb root: "Missions" under staff, "Scenario" under a story. */
  browserLabel: string;
  canvas: string;
  node: (nodeId: number) => string;
  option: (nodeId: number, optionId: number) => string;
}

export function studioPaths(
  base: StudioBase,
  templateId: number,
  storyId?: number | null
): StudioPaths {
  if (base === 'scenario') {
    return {
      browser: storyId ? `/stories/author/${storyId}` : '/stories/author',
      browserLabel: 'Scenario',
      canvas: `/stories/scenarios/${templateId}/canvas`,
      node: (nodeId: number) => `/stories/scenarios/${templateId}/nodes/${nodeId}`,
      option: (nodeId: number, optionId: number) =>
        `/stories/scenarios/${templateId}/nodes/${nodeId}/options/${optionId}`,
    };
  }
  return {
    browser: `/staff/missions?id=${templateId}`,
    browserLabel: 'Missions',
    canvas: `/staff/missions/${templateId}/canvas`,
    node: (nodeId: number) => `/staff/missions/${templateId}/nodes/${nodeId}`,
    option: (nodeId: number, optionId: number) =>
      `/staff/missions/${templateId}/nodes/${nodeId}/options/${optionId}`,
  };
}
