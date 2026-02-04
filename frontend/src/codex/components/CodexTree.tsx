import { useState, useCallback } from 'react';
import { ChevronRight, ChevronDown, FileText, Folder, FolderOpen, Loader2 } from 'lucide-react';
import type { CodexCategoryTree, CodexSubjectTreeNode } from '../types';
import { getSubjectChildren } from '../api';

interface CodexTreeProps {
  categories: CodexCategoryTree[];
  selectedEntryId?: number;
  onSelectSubject: (subjectId: number) => void;
  onSelectEntry: (entryId: number) => void;
}

export function CodexTree({
  categories,
  selectedEntryId: _selectedEntryId,
  onSelectSubject,
  onSelectEntry: _onSelectEntry,
}: CodexTreeProps) {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  // Store loaded children by subject ID
  const [loadedChildren, setLoadedChildren] = useState<Map<number, CodexSubjectTreeNode[]>>(
    new Map()
  );
  const [loadingNodes, setLoadingNodes] = useState<Set<number>>(new Set());

  const toggleNode = (nodeKey: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeKey)) {
        next.delete(nodeKey);
      } else {
        next.add(nodeKey);
      }
      return next;
    });
  };

  const loadChildren = useCallback(
    async (subjectId: number) => {
      // Already loaded or currently loading
      if (loadedChildren.has(subjectId) || loadingNodes.has(subjectId)) {
        return;
      }

      setLoadingNodes((prev) => new Set(prev).add(subjectId));
      try {
        const children = await getSubjectChildren(subjectId);
        setLoadedChildren((prev) => new Map(prev).set(subjectId, children));
      } catch (error) {
        console.error('Failed to load children:', error);
      } finally {
        setLoadingNodes((prev) => {
          const next = new Set(prev);
          next.delete(subjectId);
          return next;
        });
      }
    },
    [loadedChildren, loadingNodes]
  );

  return (
    <div className="space-y-1">
      {categories.map((category) => (
        <CategoryNode
          key={category.id}
          category={category}
          expandedNodes={expandedNodes}
          toggleNode={toggleNode}
          onSelectSubject={onSelectSubject}
          loadedChildren={loadedChildren}
          loadingNodes={loadingNodes}
          loadChildren={loadChildren}
        />
      ))}
    </div>
  );
}

interface CategoryNodeProps {
  category: CodexCategoryTree;
  expandedNodes: Set<string>;
  toggleNode: (key: string) => void;
  onSelectSubject: (subjectId: number) => void;
  loadedChildren: Map<number, CodexSubjectTreeNode[]>;
  loadingNodes: Set<number>;
  loadChildren: (subjectId: number) => void;
}

function CategoryNode({
  category,
  expandedNodes,
  toggleNode,
  onSelectSubject,
  loadedChildren,
  loadingNodes,
  loadChildren,
}: CategoryNodeProps) {
  const nodeKey = `category-${category.id}`;
  const isExpanded = expandedNodes.has(nodeKey);

  return (
    <div>
      <button
        onClick={() => toggleNode(nodeKey)}
        className="flex w-full items-center gap-1 rounded px-2 py-1 text-left hover:bg-accent"
      >
        {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        {isExpanded ? (
          <FolderOpen className="h-4 w-4 text-muted-foreground" />
        ) : (
          <Folder className="h-4 w-4 text-muted-foreground" />
        )}
        <span className="font-medium">{category.name}</span>
      </button>
      {isExpanded && (
        <div className="ml-4">
          {category.subjects.map((subject) => (
            <SubjectNode
              key={subject.id}
              subject={subject}
              parentKey={nodeKey}
              expandedNodes={expandedNodes}
              toggleNode={toggleNode}
              onSelectSubject={onSelectSubject}
              loadedChildren={loadedChildren}
              loadingNodes={loadingNodes}
              loadChildren={loadChildren}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface SubjectNodeProps {
  subject: CodexSubjectTreeNode;
  parentKey: string;
  expandedNodes: Set<string>;
  toggleNode: (key: string) => void;
  onSelectSubject: (subjectId: number) => void;
  loadedChildren: Map<number, CodexSubjectTreeNode[]>;
  loadingNodes: Set<number>;
  loadChildren: (subjectId: number) => void;
}

function SubjectNode({
  subject,
  parentKey,
  expandedNodes,
  toggleNode,
  onSelectSubject,
  loadedChildren,
  loadingNodes,
  loadChildren,
}: SubjectNodeProps) {
  const nodeKey = `${parentKey}/subject-${subject.id}`;
  const isExpanded = expandedNodes.has(nodeKey);
  const hasChildren = subject.has_children;
  const isLoading = loadingNodes.has(subject.id);
  const children = loadedChildren.get(subject.id) ?? [];

  const handleToggle = () => {
    toggleNode(nodeKey);
    // Load children when expanding if not already loaded
    if (!isExpanded && hasChildren && !loadedChildren.has(subject.id)) {
      loadChildren(subject.id);
    }
  };

  return (
    <div>
      <div className="flex items-center">
        {hasChildren ? (
          <button onClick={handleToggle} className="rounded p-0.5 hover:bg-accent">
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
        ) : (
          <span className="w-5" />
        )}
        <button
          onClick={() => onSelectSubject(subject.id)}
          className="flex flex-1 items-center gap-1 rounded px-1 py-1 text-left hover:bg-accent"
        >
          {hasChildren ? (
            isExpanded ? (
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Folder className="h-4 w-4 text-muted-foreground" />
            )
          ) : (
            <FileText className="h-4 w-4 text-muted-foreground" />
          )}
          <span>{subject.name}</span>
          {subject.entry_count > 0 && (
            <span className="text-xs text-muted-foreground">({subject.entry_count})</span>
          )}
        </button>
      </div>
      {isExpanded && hasChildren && children.length > 0 && (
        <div className="ml-4">
          {children.map((child) => (
            <SubjectNode
              key={child.id}
              subject={child}
              parentKey={nodeKey}
              expandedNodes={expandedNodes}
              toggleNode={toggleNode}
              onSelectSubject={onSelectSubject}
              loadedChildren={loadedChildren}
              loadingNodes={loadingNodes}
              loadChildren={loadChildren}
            />
          ))}
        </div>
      )}
    </div>
  );
}
