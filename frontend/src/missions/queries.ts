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
  createGiverOffering,
  createMissionGiver,
  deleteGiverOffering,
  deleteMissionGiver,
  deleteMissionInstance,
  getMissionGiver,
  getMissionTemplate,
  listGiverOfferings,
  listGiverStandings,
  listMissionGivers,
  listMissionNodes,
  listMissionOptions,
  listMissionRoutes,
  listMissionTemplates,
  listPredicateLeaves,
  listRouteCandidates,
  listRouteRewards,
  patchGiverOffering,
  patchMissionGiver,
  patchMissionNode,
  patchMissionTemplate,
} from './api';
import type { PredicateLeaf, PredicateLeafParam, PredicateParamType } from './api';
export type { PredicateLeaf, PredicateLeafParam, PredicateParamType };
import type {
  MissionGiver,
  MissionGiverOffering,
  MissionGiverStanding,
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
  templateDetail: (slug: string) => [...missionKeys.templates(), 'detail', slug] as const,
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
  givers: () => [...missionKeys.all, 'givers'] as const,
  giverList: (filters: object) => [...missionKeys.givers(), 'list', filters] as const,
  giverDetail: (slug: string) => [...missionKeys.givers(), 'detail', slug] as const,
  offerings: () => [...missionKeys.all, 'offerings'] as const,
  offeringsFor: (filters: object) => [...missionKeys.offerings(), filters] as const,
  standings: () => [...missionKeys.all, 'standings'] as const,
  standingsFor: (filters: object) => [...missionKeys.standings(), filters] as const,
  predicateLeaves: () => [...missionKeys.all, 'predicate-leaves'] as const,
};

const FIVE_MINUTES = 5 * 60 * 1000;

export function useMissionTemplates(
  filters: MissionTemplateFilters & { page?: number } = {}
): UseQueryResult<PaginatedResponse<MissionTemplate>> {
  return useQuery({
    queryKey: missionKeys.templateList(filters),
    queryFn: () => listMissionTemplates(filters),
    staleTime: 30_000,
    throwOnError: true,
  });
}

export function useMissionTemplate(
  slug: string | undefined
): UseQueryResult<MissionTemplateDetail> {
  return useQuery({
    queryKey: missionKeys.templateDetail(slug ?? ''),
    queryFn: () => getMissionTemplate(slug as string),
    enabled: Boolean(slug),
    throwOnError: true,
  });
}

export function useMissionNodes(
  filters: {
    template?: number;
    template_slug?: string;
    is_entry?: boolean;
    needs_rewrite?: boolean;
  } = {}
): UseQueryResult<PaginatedResponse<MissionNode>> {
  return useQuery({
    queryKey: missionKeys.nodesFor(filters),
    queryFn: () => listMissionNodes(filters),
    throwOnError: true,
  });
}

export function useMissionOptions(
  filters: { node?: number; template?: number; needs_rewrite?: boolean } = {}
): UseQueryResult<PaginatedResponse<MissionOption>> {
  return useQuery({
    queryKey: missionKeys.optionsFor(filters),
    queryFn: () => listMissionOptions(filters),
    enabled: Boolean(filters.node ?? filters.template),
    throwOnError: true,
  });
}

export function useMissionRoutes(
  filters: { option?: number; template?: number; needs_rewrite?: boolean } = {}
): UseQueryResult<PaginatedResponse<MissionOptionRoute>> {
  return useQuery({
    queryKey: missionKeys.routesFor(filters),
    queryFn: () => listMissionRoutes(filters),
    enabled: Boolean(filters.option ?? filters.template),
    throwOnError: true,
  });
}

export function useRouteCandidates(
  filters: { route?: number } = {}
): UseQueryResult<PaginatedResponse<MissionOptionRouteCandidate>> {
  return useQuery({
    queryKey: missionKeys.candidatesFor(filters),
    queryFn: () => listRouteCandidates(filters),
    enabled: Boolean(filters.route),
    throwOnError: true,
  });
}

export function useRouteRewards(
  filters: { route?: number; candidate?: number } = {}
): UseQueryResult<PaginatedResponse<MissionOptionRouteReward>> {
  return useQuery({
    queryKey: missionKeys.rewardsFor(filters),
    queryFn: () => listRouteRewards(filters),
    enabled: Boolean(filters.route ?? filters.candidate),
    throwOnError: true,
  });
}

export function useMissionGivers(
  filters: {
    org?: number;
    org_name?: string;
    giver_kind?: string;
    is_active?: boolean;
    name?: string;
  } = {}
): UseQueryResult<PaginatedResponse<MissionGiver>> {
  return useQuery({
    queryKey: missionKeys.giverList(filters),
    queryFn: () => listMissionGivers(filters),
    throwOnError: true,
  });
}

export function useMissionGiver(slug: string | undefined): UseQueryResult<MissionGiver> {
  return useQuery({
    queryKey: missionKeys.giverDetail(slug ?? ''),
    queryFn: () => getMissionGiver(slug as string),
    enabled: Boolean(slug),
    throwOnError: true,
  });
}

export function useGiverOfferings(
  filters: { giver?: number; template?: number } = {}
): UseQueryResult<PaginatedResponse<MissionGiverOffering>> {
  return useQuery({
    queryKey: missionKeys.offeringsFor(filters),
    queryFn: () => listGiverOfferings(filters),
    enabled: Boolean(filters.giver ?? filters.template),
    throwOnError: true,
  });
}

export function useGiverStandings(
  filters: { giver?: number; character?: number } = {}
): UseQueryResult<PaginatedResponse<MissionGiverStanding>> {
  return useQuery({
    queryKey: missionKeys.standingsFor(filters),
    queryFn: () => listGiverStandings(filters),
    enabled: Boolean(filters.giver ?? filters.character),
    throwOnError: true,
  });
}

export function usePredicateLeaves(): UseQueryResult<PredicateLeaf[]> {
  return useQuery({
    queryKey: missionKeys.predicateLeaves(),
    queryFn: listPredicateLeaves,
    staleTime: FIVE_MINUTES,
    throwOnError: true,
  });
}

// ---------------------------------------------------------------------------
// Mutations — invalidate the closest parent key on success.
// ---------------------------------------------------------------------------

export function usePatchMissionTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, body }: { slug: string; body: Partial<MissionTemplate> }) =>
      patchMissionTemplate(slug, body),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: missionKeys.templateDetail(slug) });
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
    mutationFn: ({
      slug,
      new_slug,
      new_name,
    }: {
      slug: string;
      new_slug: string;
      new_name: string;
    }) => copyTemplate(slug, { new_slug, new_name }),
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
    mutationFn: ({ slug, character }: { slug: string; character: number }) =>
      assignMission(slug, { character }),
    onSuccess: (_inst: MissionInstance, { slug }) => {
      qc.invalidateQueries({ queryKey: missionKeys.templateDetail(slug) });
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

export function useCreateMissionGiver() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<MissionGiver>) => createMissionGiver(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.givers() }),
  });
}

export function usePatchMissionGiver() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, body }: { slug: string; body: Partial<MissionGiver> }) =>
      patchMissionGiver(slug, body),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: missionKeys.giverDetail(slug) });
      qc.invalidateQueries({ queryKey: missionKeys.givers() });
    },
  });
}

export function useDeleteMissionGiver() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => deleteMissionGiver(slug),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.givers() }),
  });
}

export function useCreateGiverOffering() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<MissionGiverOffering>) => createGiverOffering(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.offerings() }),
  });
}

export function usePatchGiverOffering() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<MissionGiverOffering> }) =>
      patchGiverOffering(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.offerings() }),
  });
}

export function useDeleteGiverOffering() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteGiverOffering(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: missionKeys.offerings() }),
  });
}
