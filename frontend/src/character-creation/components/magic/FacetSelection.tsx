/**
 * FacetSelection Component
 *
 * Allows players to select facets (imagery/symbolism) for their motif resonances.
 * Rules:
 * - Only leaf-level facets (depth 2+) are selectable
 * - Max 5 facets per resonance
 * - A facet can only be assigned to one resonance
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { ChevronDown, ChevronRight, Leaf, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  useCreateDraftFacetAssignment,
  useDeleteDraftFacetAssignment,
  useDraftMotif,
  useFacetTree,
  useResonances,
} from '../../queries';
import type { DraftMotifResonance, FacetTreeNode } from '../../types';

const MAX_FACETS_PER_RESONANCE = 5;

interface FacetSelectionProps {
  /** Optional callback when facet selection changes */
  onChange?: () => void;
}

export function FacetSelection({ onChange }: FacetSelectionProps) {
  const { data: facetTree, isLoading: facetsLoading } = useFacetTree();
  const { data: motif, isLoading: motifLoading } = useDraftMotif();
  const { data: resonances } = useResonances();
  const createFacetAssignment = useCreateDraftFacetAssignment();
  const deleteFacetAssignment = useDeleteDraftFacetAssignment();

  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [selectedResonanceId, setSelectedResonanceId] = useState<number | null>(null);

  // Get resonance name by ID
  const getResonanceName = (resonanceId: number) => {
    return resonances?.find((r) => r.id === resonanceId)?.name ?? 'Unknown';
  };

  // Build a map of facet ID -> assigned resonance ID
  const facetAssignments = useMemo(() => {
    const map = new Map<number, { resonanceId: number; assignmentId: number }>();
    if (!motif?.resonances) return map;

    for (const resonance of motif.resonances) {
      for (const assignment of resonance.facet_assignments) {
        map.set(assignment.facet, {
          resonanceId: resonance.resonance,
          assignmentId: assignment.id,
        });
      }
    }
    return map;
  }, [motif]);

  // Count facets per resonance
  const facetCountByResonance = useMemo(() => {
    const counts = new Map<number, number>();
    if (!motif?.resonances) return counts;

    for (const resonance of motif.resonances) {
      counts.set(resonance.resonance, resonance.facet_assignments.length);
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

  const handleSelectFacet = async (facetId: number) => {
    if (!selectedResonanceId) return;

    const motifResonance = getMotifResonance(selectedResonanceId);
    if (!motifResonance) {
      console.error('No motif resonance found for', selectedResonanceId);
      return;
    }

    // Check if facet is already assigned
    const existing = facetAssignments.get(facetId);
    if (existing) {
      // If assigned to same resonance, remove it
      if (existing.resonanceId === selectedResonanceId) {
        await deleteFacetAssignment.mutateAsync(existing.assignmentId);
        onChange?.();
      }
      // If assigned to different resonance, do nothing (can't reassign)
      return;
    }

    // Check max facets per resonance
    const currentCount = facetCountByResonance.get(selectedResonanceId) ?? 0;
    if (currentCount >= MAX_FACETS_PER_RESONANCE) {
      return;
    }

    // Create assignment
    await createFacetAssignment.mutateAsync({
      motif_resonance: motifResonance.id,
      facet: facetId,
    });
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

  // Recursively render facet tree
  const renderFacetNode = (node: FacetTreeNode, depth: number = 0) => {
    const hasChildren = node.children && node.children.length > 0;
    const isLeaf = !hasChildren;
    const isExpanded = expandedCategories.has(node.name);

    // Get assignment status for this facet
    const assignment = facetAssignments.get(node.id);
    const isAssigned = !!assignment;
    const isAssignedToSelected = assignment?.resonanceId === selectedResonanceId;
    const isAssignedToOther = isAssigned && !isAssignedToSelected;

    // Check if this resonance is full
    const currentCount = selectedResonanceId
      ? (facetCountByResonance.get(selectedResonanceId) ?? 0)
      : 0;
    const isFull = currentCount >= MAX_FACETS_PER_RESONANCE;

    // Only leaf nodes are selectable
    const isSelectable = isLeaf && selectedResonanceId && !isAssignedToOther && !isFull;

    if (hasChildren) {
      // Category node
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
            <div className="pl-4">
              {node.children.map((child) => renderFacetNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    // Leaf node (selectable facet)
    return (
      <button
        key={node.id}
        type="button"
        disabled={!isSelectable && !isAssignedToSelected}
        onClick={() => handleSelectFacet(node.id)}
        className={cn(
          'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
          isAssignedToSelected && 'bg-primary/20 text-primary',
          isAssignedToOther && 'cursor-not-allowed opacity-50',
          !isAssigned && isSelectable && 'cursor-pointer hover:bg-muted',
          !isAssigned && !isSelectable && 'cursor-not-allowed opacity-50'
        )}
      >
        <Leaf className="h-3 w-3" />
        {node.name}
        {isAssigned && (
          <Badge variant="secondary" className="ml-auto text-xs">
            {getResonanceName(assignment.resonanceId)}
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
          <CardDescription>Design your gift first to unlock facet selection.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Facets are imagery and symbolism that define your magical aesthetic. Create a gift with
            resonances to start selecting facets.
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
          Select imagery and symbolism for each resonance (max {MAX_FACETS_PER_RESONANCE} per
          resonance).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Resonance selector */}
        <div className="space-y-2">
          <label className="text-sm font-medium">Select a Resonance</label>
          <div className="flex flex-wrap gap-2">
            {motif.resonances.map((mr) => {
              const count = facetCountByResonance.get(mr.resonance) ?? 0;
              const isSelected = selectedResonanceId === mr.resonance;
              return (
                <Button
                  key={mr.id}
                  variant={isSelected ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setSelectedResonanceId(mr.resonance)}
                >
                  {getResonanceName(mr.resonance)}
                  <Badge variant="secondary" className="ml-2">
                    {count}/{MAX_FACETS_PER_RESONANCE}
                  </Badge>
                </Button>
              );
            })}
          </div>
        </div>

        {/* Selected resonance's facets */}
        {selectedResonanceId && (
          <div className="space-y-2">
            <label className="text-sm font-medium">
              Facets for {getResonanceName(selectedResonanceId)}
            </label>
            <div className="flex flex-wrap gap-2">
              {getMotifResonance(selectedResonanceId)?.facet_assignments.map((fa) => {
                const facetName = facetTree ? findFacetName(facetTree, fa.facet) : 'Unknown';
                return (
                  <Badge key={fa.id} variant="default" className="gap-1">
                    {facetName}
                    <button
                      type="button"
                      onClick={() => handleRemoveFacet(fa.id)}
                      className="ml-1 rounded-full hover:bg-primary-foreground/20"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                );
              })}
              {(facetCountByResonance.get(selectedResonanceId) ?? 0) === 0 && (
                <span className="text-sm text-muted-foreground">
                  No facets selected. Browse below to add facets.
                </span>
              )}
            </div>
          </div>
        )}

        {/* Facet browser */}
        <div className="space-y-2">
          <label className="text-sm font-medium">Browse Facets</label>
          {!selectedResonanceId ? (
            <p className="text-sm text-muted-foreground">
              Select a resonance above to start adding facets.
            </p>
          ) : (
            <div className="max-h-64 overflow-y-auto rounded-md border p-2">
              {facetTree?.map((node) => renderFacetNode(node))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
