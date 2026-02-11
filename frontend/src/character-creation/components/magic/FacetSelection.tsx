/**
 * FacetSelection Component
 *
 * Redesigned: Global facet view with primary resonance assignment.
 *
 * - Shows all currently assigned facets globally (with their primary resonance labeled)
 * - "Add Facet" opens the facet tree browser
 * - After selecting a facet, pick which resonance to link it to
 * - Shows which other resonances this facet is shared with (based on affinity rules)
 *
 * Affinity sharing rules:
 * - Abyssal resonance facet: shared by all Abyssal + Primal resonances (not Celestial)
 * - Celestial resonance facet: shared by all Celestial + Primal resonances (not Abyssal)
 * - Primal resonance facet: shared by everything EXCEPT the specific opposite primal resonance
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { ChevronDown, ChevronRight, Leaf, Plus, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  useCreateDraftFacetAssignment,
  useDeleteDraftFacetAssignment,
  useDraftMotif,
  useFacetTree,
  useResonances,
} from '../../queries';
import type { DraftMotifResonance, FacetTreeNode, Resonance } from '../../types';

const MAX_FACETS_PER_RESONANCE = 5;

interface FacetSelectionProps {
  /** Optional callback when facet selection changes */
  onChange?: () => void;
}

/**
 * Given a resonance, compute which other resonances share facets with it
 * based on the affinity rules.
 */
function getSharedResonances(primaryResonance: Resonance, allResonances: Resonance[]): Resonance[] {
  const affinity = primaryResonance.resonance_affinity;
  if (!affinity) return [];

  return allResonances.filter((r) => {
    if (r.id === primaryResonance.id) return false;
    if (!r.resonance_affinity) return false;

    if (affinity === 'abyssal') {
      // Shared by Abyssal + Primal (not Celestial)
      return r.resonance_affinity === 'abyssal' || r.resonance_affinity === 'primal';
    }
    if (affinity === 'celestial') {
      // Shared by Celestial + Primal (not Abyssal)
      return r.resonance_affinity === 'celestial' || r.resonance_affinity === 'primal';
    }
    if (affinity === 'primal') {
      // Shared by everything EXCEPT the specific opposite primal resonance
      if (primaryResonance.opposite === r.id) return false;
      return true;
    }
    return false;
  });
}

export function FacetSelection({ onChange }: FacetSelectionProps) {
  const { data: facetTree, isLoading: facetsLoading } = useFacetTree();
  const { data: motif, isLoading: motifLoading } = useDraftMotif();
  const { data: resonances } = useResonances();
  const createFacetAssignment = useCreateDraftFacetAssignment();
  const deleteFacetAssignment = useDeleteDraftFacetAssignment();

  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [showBrowser, setShowBrowser] = useState(false);
  const [pendingFacetId, setPendingFacetId] = useState<number | null>(null);

  // Get resonance by ID
  const getResonance = (resonanceId: number): Resonance | undefined => {
    return resonances?.find((r) => r.id === resonanceId);
  };

  const getResonanceName = (resonanceId: number) => {
    return getResonance(resonanceId)?.name ?? 'Unknown';
  };

  // Build a flat list of all facet assignments across all resonances
  const allAssignments = useMemo(() => {
    if (!motif?.resonances) return [];
    const result: Array<{
      assignmentId: number;
      facetId: number;
      resonanceId: number;
      motifResonanceId: number;
    }> = [];
    for (const mr of motif.resonances) {
      for (const fa of mr.facet_assignments) {
        result.push({
          assignmentId: fa.id,
          facetId: fa.facet,
          resonanceId: mr.resonance,
          motifResonanceId: mr.id,
        });
      }
    }
    return result;
  }, [motif]);

  // Set of already-assigned facet IDs
  const assignedFacetIds = useMemo(() => {
    return new Set(allAssignments.map((a) => a.facetId));
  }, [allAssignments]);

  // Count facets per resonance
  const facetCountByResonance = useMemo(() => {
    const counts = new Map<number, number>();
    if (!motif?.resonances) return counts;
    for (const mr of motif.resonances) {
      counts.set(mr.resonance, mr.facet_assignments.length);
    }
    return counts;
  }, [motif]);

  // Get the DraftMotifResonance record for a given resonance ID
  const getMotifResonance = (resonanceId: number): DraftMotifResonance | undefined => {
    return motif?.resonances.find((r) => r.resonance === resonanceId);
  };

  const toggleCategory = (categoryName: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(categoryName)) {
        next.delete(categoryName);
      } else {
        next.add(categoryName);
      }
      return next;
    });
  };

  const handleSelectFacetFromTree = (facetId: number) => {
    if (assignedFacetIds.has(facetId)) return;
    // If only one resonance, auto-assign
    if (motif?.resonances.length === 1) {
      handleAssignFacet(facetId, motif.resonances[0].resonance);
      return;
    }
    // Otherwise, prompt user to pick a resonance
    setPendingFacetId(facetId);
  };

  const handleAssignFacet = async (facetId: number, resonanceId: number) => {
    const mr = getMotifResonance(resonanceId);
    if (!mr) return;

    const count = facetCountByResonance.get(resonanceId) ?? 0;
    if (count >= MAX_FACETS_PER_RESONANCE) return;

    await createFacetAssignment.mutateAsync({
      motif_resonance: mr.id,
      facet: facetId,
    });
    setPendingFacetId(null);
    onChange?.();
  };

  const handleRemoveFacet = async (assignmentId: number) => {
    await deleteFacetAssignment.mutateAsync(assignmentId);
    onChange?.();
  };

  // Find facet name by ID from tree
  const findFacetName = (nodes: FacetTreeNode[], facetId: number): string => {
    for (const node of nodes) {
      if (node.id === facetId) return node.name;
      if (node.children) {
        const found = findFacetName(node.children, facetId);
        if (found !== 'Unknown') return found;
      }
    }
    return 'Unknown';
  };

  // Recursively render facet tree for browsing
  const renderFacetNode = (node: FacetTreeNode) => {
    const hasChildren = node.children && node.children.length > 0;
    const isLeaf = !hasChildren;
    const isExpanded = expandedCategories.has(node.name);
    const isAssigned = assignedFacetIds.has(node.id);
    const isSelectable = isLeaf && !isAssigned;

    if (hasChildren) {
      return (
        <div key={node.id}>
          <button
            type="button"
            onClick={() => toggleCategory(node.name)}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium hover:bg-muted"
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            {node.name}
            <span className="text-xs text-muted-foreground">({node.children.length})</span>
          </button>
          {isExpanded && (
            <div className="pl-4">{node.children.map((child) => renderFacetNode(child))}</div>
          )}
        </div>
      );
    }

    return (
      <button
        key={node.id}
        type="button"
        disabled={!isSelectable}
        onClick={() => handleSelectFacetFromTree(node.id)}
        className={cn(
          'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
          isAssigned && 'cursor-not-allowed opacity-50',
          isSelectable && 'cursor-pointer hover:bg-muted'
        )}
      >
        <Leaf className="h-3 w-3" />
        {node.name}
        {isAssigned && (
          <Badge variant="secondary" className="ml-auto text-xs">
            Assigned
          </Badge>
        )}
      </button>
    );
  };

  if (facetsLoading || motifLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Facets</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-40 animate-pulse rounded bg-muted" />
        </CardContent>
      </Card>
    );
  }

  if (!motif || !motif.resonances || motif.resonances.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Facets</CardTitle>
          <CardDescription>Your motif is being set up...</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Facets are imagery and symbolism that define your magical aesthetic. Your motif
            resonances will appear here once your gift is created.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Facets</CardTitle>
        <CardDescription>
          Select imagery and symbolism for your motif. Each facet is linked to a primary resonance
          and shared across compatible resonances based on affinity.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Global facet list */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">Your Facets</label>
            <Button variant="outline" size="sm" onClick={() => setShowBrowser(!showBrowser)}>
              <Plus className="mr-1 h-3 w-3" />
              {showBrowser ? 'Close Browser' : 'Add Facet'}
            </Button>
          </div>

          {allAssignments.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {allAssignments.map((assignment) => {
                const facetName = facetTree
                  ? findFacetName(facetTree, assignment.facetId)
                  : 'Unknown';
                const primaryResonance = getResonance(assignment.resonanceId);
                const sharedWith =
                  primaryResonance && resonances
                    ? getSharedResonances(primaryResonance, resonances)
                        .filter((r) => motif.resonances.some((mr) => mr.resonance === r.id))
                        .map((r) => r.name)
                    : [];
                return (
                  <div
                    key={assignment.assignmentId}
                    className="flex items-center gap-1.5 rounded-md border px-2 py-1"
                  >
                    <Leaf className="h-3 w-3 text-muted-foreground" />
                    <span className="text-sm font-medium">{facetName}</span>
                    <Badge variant="secondary" className="text-xs">
                      {getResonanceName(assignment.resonanceId)}
                    </Badge>
                    {sharedWith.length > 0 && (
                      <span className="text-xs text-muted-foreground">
                        +{sharedWith.join(', ')}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => handleRemoveFacet(assignment.assignmentId)}
                      className="ml-1 rounded-full hover:bg-destructive/20"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No facets selected yet. Click "Add Facet" to browse and add facets.
            </p>
          )}
        </div>

        {/* Resonance picker for pending facet */}
        {pendingFacetId && (
          <div className="space-y-2 rounded-md border border-primary/50 bg-primary/5 p-3">
            <label className="text-sm font-medium">
              Link "{facetTree ? findFacetName(facetTree, pendingFacetId) : '...'}" to which
              resonance?
            </label>
            <div className="flex flex-wrap gap-2">
              {motif.resonances.map((mr) => {
                const count = facetCountByResonance.get(mr.resonance) ?? 0;
                const isFull = count >= MAX_FACETS_PER_RESONANCE;
                return (
                  <Button
                    key={mr.id}
                    variant="outline"
                    size="sm"
                    disabled={isFull}
                    onClick={() => handleAssignFacet(pendingFacetId, mr.resonance)}
                  >
                    {getResonanceName(mr.resonance)}
                    <Badge variant="secondary" className="ml-2">
                      {count}/{MAX_FACETS_PER_RESONANCE}
                    </Badge>
                  </Button>
                );
              })}
              <Button variant="ghost" size="sm" onClick={() => setPendingFacetId(null)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Facet browser */}
        {showBrowser && (
          <div className="space-y-2">
            <label className="text-sm font-medium">Browse Facets</label>
            <div className="max-h-64 overflow-y-auto rounded-md border p-2">
              {facetTree?.map((node) => renderFacetNode(node))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
