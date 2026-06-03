/**
 * Mission Studio React Query hooks.
 *
 * Hierarchical key namespace per project convention. Mutations
 * invalidate the closest parent key so the Studio's listing/detail
 * views update on copy/assign/edit without manual refetch glue.
 */

import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import {
  assignMission,
  copyNode,
  copySubtree,
  copyTemplate,
  createMissionTemplate,
  deleteMissionInstance,
  getMissionTemplate,
  listMissionCategories,
  listMissionNodes,
  listMissionOptions,
  listMissionRoutes,
  listMissionTemplates,
  listPredicateLeaves,
  listRouteCandidates,
  listRouteRewards,
  patchMissionNode,
  patchMissionTemplate,
} from './api';
import type { PredicateLeaf, PredicateLeafParam, PredicateParamType } from './api';
export type { PredicateLeaf, PredicateLeafParam, PredicateParamType };
import type {
  MissionCategory,
  MissionInstance,
  MissionNode,
  MissionOption,
  MissionOptionRoute,
  MissionOptionRouteCandidate,
  MissionOptionRouteReward,
  MissionTemplate,
  MissionTemplateDetail,
  MissionTemplateFilters,
  PaginatedResponse,
} from './types';

export const missionKeys = {
  all: ['missions'] as const,
  templates: () => [...missionKeys.all, 'templates'] as const,
  templateList: (filters: MissionTemplateFilters & { page?: number }) =>
    [...missionKeys.templates(), 'list', filters] as const,
  templateDetail: (id: number) => [...missionKeys.templates(), 'detail', id] as const,
  nodes: () => [...missionKeys.all, 'nodes'] as const,
  nodesFor: (filters: object) => [...missionKeys.nodes(), filters] as const,
  options: () => [...missionKeys.all, 'options'] as const,
  optionsFor: (filters: object) => [...missionKeys.options(), filters] as const,
  routes: () => [...missionKeys.all, 'routes'] as const,
  routesFor: (filters: object) => [...missionKeys.routes(), filters] as const,
  candidates: () => [...missionKeys.all, 'candidates'] as const,
  candidatesFor: (filters: object) => [...missionKeys.candidates(), filters] as const,
  rewards: () => [...missionKeys.all, 'rewards'] as const,
  rewardsFor: (filters: object) => [...missionKeys.rewards(), filters] as const,
  predicateLeaves: () => [...missionKeys.all, 'predicate-leaves'] as const,
  categories: () => [...missionKeys.all, 'categories'] as const,
};

const FIVE_MINUTES = 5 * 60 * 1000;

export function useMissionTemplates(
  filters: MissionTemplateFilters & { page?: number } = {}
): UseQueryResult<PaginatedResponse<MissionTemplate>> {
  return useQuery({
    queryKey: missionKeys.templateList(filters),
    queryFn: () => listMissionTemplates(filters),
    staleTime: 30_000,
    // No throwOnError: MissionBrowserPage handles isError inline so a list
    // fetch failure shows a "couldn't load" card rather than crashing to the
    // global ErrorBoundary. Other drill-down hooks still use throwOnError —
    // tracked as a follow-up to align them; out of scope for this PR.
  });
}

export function useMissionTemplate(id: number | undefined): UseQueryResult<MissionTemplateDetail> {
  return useQuery({
    queryKey: missionKeys.templateDetail(id ?? 0),
    queryFn: () => getMissionTemplate(id as number),
    enabled: id !== undefined && id !== 0 && Number.isFinite(id),
  });
}

export function useMissionNodes(
  filters: {
    template?: number;
    is_entry?: boolean;
    needs_rewrite?: boolean;
  } = {}
): UseQueryResult<PaginatedResponse<MissionNode>> {
  return useQuery({
    queryKey: missionKeys.nodesFor(filters),
    queryFn: () => listMissionNodes(filters),
    // Consumers check isError and render inline so a fetch failure doesn't
    // nuke the whole drill-down view.
  });
}

export function useMissionOptions(
  filters: { node?: number; template?: number; needs_rewrite?: boolean } = {}
): UseQueryResult<PaginatedResponse<MissionOption>> {
  return useQuery({
    queryKey: missionKeys.optionsFor(filters),
    queryFn: () => listMissionOptions(filters),
    enabled: Boolean(filters.node ?? filters.template),
    // Consumers check isError and render inline so a fetch failure doesn't
    // nuke the whole drill-down view.
  });
}

export function useMissionRoutes(
  filters: { option?: number; template?: number; needs_rewrite?: boolean } = {}
): UseQueryResult<PaginatedResponse<MissionOptionRoute>> {
  return useQuery({
    queryKey: missionKeys.routesFor(filters),
    queryFn: () => listMissionRoutes(filters),
    enabled: Boolean(filters.option ?? filters.template),
    // Consumers check isError and render inline so a fetch failure doesn't
    // nuke the whole drill-down view.
  });
}

export function useRouteCandidates(
  filters: { route?: number } = {}
): UseQueryResult<PaginatedResponse<MissionOptionRouteCandidate>> {
  return useQuery({
    queryKey: missionKeys.candidatesFor(filters),
    queryFn: () => listRouteCandidates(filters),
    enabled: Boolean(filters.route),
    // Consumers check isError and render inline so a fetch failure doesn't
    // nuke the whole drill-down view.
  });
}

export function useRouteRewards(
  filters: { route?: number; candidate?: number } = {}
): UseQueryResult<PaginatedResponse<MissionOptionRouteReward>> {
  return useQuery({
    queryKey: missionKeys.rewardsFor(filters),
    queryFn: () => listRouteRewards(filters),
    enabled: Boolean(filters.route ?? filters.candidate),
    // Consumers check isError and render inline so a fetch failure doesn't
    // nuke the whole drill-down view.
  });
}

export function usePredicateLeaves(): UseQueryResult<PredicateLeaf[]> {
  return useQuery({
    queryKey: missionKeys.predicateLeaves(),
    queryFn: listPredicateLeaves,
    staleTime: FIVE_MINUTES,
    // Consumers check isError and render inline so a fetch failure doesn't
    // nuke the whole drill-down view.
  });
}

// ---------------------------------------------------------------------------
// Mutations — invalidate the closest parent key on success.
// ---------------------------------------------------------------------------

export function usePatchMissionTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<MissionTemplate> }) =>
      patchMissionTemplate(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: missionKeys.templateDetail(id) });
      qc.invalidateQueries({ queryKey: missionKeys.templates() });
    },
  });
}

export function usePatchMissionNode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<MissionNode> }) =>
      patchMissionNode(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: missionKeys.nodes() });
    },
  });
}

export function useCopyTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, new_name }: { id: number; new_name?: string }) =>
      copyTemplate(id, { new_name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.templates() }),
  });
}

export function useCopyNode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, new_key }: { id: number; new_key: string }) => copyNode(id, { new_key }),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.nodes() }),
  });
}

export function useCopySubtree() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, new_key_prefix }: { id: number; new_key_prefix: string }) =>
      copySubtree(id, { new_key_prefix }),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.nodes() }),
  });
}

export function useAssignMission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, character }: { id: number; character: number }) =>
      assignMission(id, { character }),
    onSuccess: (_inst: MissionInstance, { id }) => {
      qc.invalidateQueries({ queryKey: missionKeys.templateDetail(id) });
    },
  });
}

export function useDeleteMissionInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteMissionInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.templates() }),
  });
}

export function useCreateMissionTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<MissionTemplate>) => createMissionTemplate(body),
    onSuccess: (created) => {
      // Prime the detail cache with the create response so MissionCanvasPage
      // renders instantly on the post-create navigate instead of firing a
      // cold fetch and showing a spinner. Invalidate the list so the browser
      // shows the new row.
      qc.setQueryData(missionKeys.templateDetail(created.id), created);
      qc.invalidateQueries({ queryKey: missionKeys.templates() });
    },
  });
}

export function useMissionCategories(): UseQueryResult<PaginatedResponse<MissionCategory>> {
  return useQuery({
    queryKey: missionKeys.categories(),
    queryFn: listMissionCategories,
    staleTime: FIVE_MINUTES,
    // Intentionally no throwOnError here: the picker consumers (CreateMissionPage,
    // EditCategoriesDialog) check isError and render inline so a categories
    // fetch failure doesn't nuke the user's half-filled form.
  });
}
