import { useState, useCallback, useEffect, useRef } from 'react';
import { ChevronRight, ChevronDown, FileText, Folder, FolderOpen, Loader2 } from 'lucide-react';
import type { CodexCategoryTree, CodexSubjectTreeNode } from '../types';
import { getSubjectChildren } from '../api';

interface CodexTreeProps {
  categories: CodexCategoryTree[];
  selectedCategoryId?: number;
  selectedSubjectId?: number;
  selectedEntryId?: number;
  onSelectCategory: (categoryId: number) => void;
  onSelectSubject: (subjectId: number) => void;
  onSelectEntry: (entryId: number) => void;
}

export function CodexTree({
  categories,
  selectedCategoryId,
  selectedSubjectId,
  selectedEntryId: _selectedEntryId,
  onSelectCategory,
  onSelectSubject,
  onSelectEntry: _onSelectEntry,
}: CodexTreeProps) {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [loadedChildren, setLoadedChildren] = useState<Map<number, CodexSubjectTreeNode[]>>(
    new Map()
  );
  const [loadingNodes, setLoadingNodes] = useState<Set<number>>(new Set());
  const selectedRef = useRef<HTMLButtonElement>(null);

  // Auto-expand to show selected category
  useEffect(() => {
    if (selectedCategoryId) {
      setExpandedNodes((prev) => {
        const next = new Set(prev);
        next.add(`category-${selectedCategoryId}`);
        return next;
      });
    }
  }, [selectedCategoryId]);

  // Auto-expand to show selected subject (simplified - expands category containing it)
  useEffect(() => {
    if (selectedSubjectId) {
      // Find which category contains this subject
      for (const category of categories) {
        const hasSubject = category.subjects.some((s) => s.id === selectedSubjectId);
        if (hasSubject) {
          setExpandedNodes((prev) => {
            const next = new Set(prev);
            next.add(`category-${category.id}`);
            return next;
          });
          break;
        }
      }
    }
  }, [selectedSubjectId, categories]);

  // Scroll selected item into view
  useEffect(() => {
    if (selectedRef.current) {
      selectedRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [selectedCategoryId, selectedSubjectId]);

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
          selectedCategoryId={selectedCategoryId}
          selectedSubjectId={selectedSubjectId}
          onSelectCategory={onSelectCategory}
          onSelectSubject={onSelectSubject}
          loadedChildren={loadedChildren}
          loadingNodes={loadingNodes}
          loadChildren={loadChildren}
          selectedRef={selectedRef}
        />
      ))}
    </div>
  );
}

interface CategoryNodeProps {
  category: CodexCategoryTree;
  expandedNodes: Set<string>;
  toggleNode: (key: string) => void;
  selectedCategoryId?: number;
  selectedSubjectId?: number;
  onSelectCategory: (categoryId: number) => void;
  onSelectSubject: (subjectId: number) => void;
  loadedChildren: Map<number, CodexSubjectTreeNode[]>;
  loadingNodes: Set<number>;
  loadChildren: (subjectId: number) => void;
  selectedRef: React.RefObject<HTMLButtonElement>;
}

function CategoryNode({
  category,
  expandedNodes,
  toggleNode,
  selectedCategoryId,
  selectedSubjectId,
  onSelectCategory,
  onSelectSubject,
  loadedChildren,
  loadingNodes,
  loadChildren,
  selectedRef,
}: CategoryNodeProps) {
  const nodeKey = `category-${category.id}`;
  const isExpanded = expandedNodes.has(nodeKey);
  const isSelected = selectedCategoryId === category.id && !selectedSubjectId;

  const handleChevronClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    toggleNode(nodeKey);
  };

  return (
    <div>
      <div className="flex items-center">
        <button onClick={handleChevronClick} className="rounded p-0.5 hover:bg-accent">
          {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <button
          ref={isSelected ? selectedRef : undefined}
          onClick={() => onSelectCategory(category.id)}
          className={`flex flex-1 items-center gap-1 rounded px-1 py-1 text-left hover:bg-accent ${
            isSelected ? 'bg-accent' : ''
          }`}
        >
          {isExpanded ? (
            <FolderOpen className="h-4 w-4 text-muted-foreground" />
          ) : (
            <Folder className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="font-medium">{category.name}</span>
        </button>
      </div>
      {isExpanded && (
        <div className="ml-4">
          {category.subjects.map((subject) => (
            <SubjectNode
              key={subject.id}
              subject={subject}
              parentKey={nodeKey}
              expandedNodes={expandedNodes}
              toggleNode={toggleNode}
              selectedSubjectId={selectedSubjectId}
              onSelectSubject={onSelectSubject}
              loadedChildren={loadedChildren}
              loadingNodes={loadingNodes}
              loadChildren={loadChildren}
              selectedRef={selectedRef}
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
  selectedSubjectId?: number;
  onSelectSubject: (subjectId: number) => void;
  loadedChildren: Map<number, CodexSubjectTreeNode[]>;
  loadingNodes: Set<number>;
  loadChildren: (subjectId: number) => void;
  selectedRef: React.RefObject<HTMLButtonElement>;
}

function SubjectNode({
  subject,
  parentKey,
  expandedNodes,
  toggleNode,
  selectedSubjectId,
  onSelectSubject,
  loadedChildren,
  loadingNodes,
  loadChildren,
  selectedRef,
}: SubjectNodeProps) {
  const nodeKey = `${parentKey}/subject-${subject.id}`;
  const isExpanded = expandedNodes.has(nodeKey);
  const hasChildren = subject.has_children;
  const isLoading = loadingNodes.has(subject.id);
  const children = loadedChildren.get(subject.id) ?? [];
  const isSelected = selectedSubjectId === subject.id;

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    toggleNode(nodeKey);
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
          ref={isSelected ? selectedRef : undefined}
          onClick={() => onSelectSubject(subject.id)}
          className={`flex flex-1 items-center gap-1 rounded px-1 py-1 text-left hover:bg-accent ${
            isSelected ? 'bg-accent' : ''
          }`}
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
              selectedSubjectId={selectedSubjectId}
              onSelectSubject={onSelectSubject}
              loadedChildren={loadedChildren}
              loadingNodes={loadingNodes}
              loadChildren={loadChildren}
              selectedRef={selectedRef}
            />
          ))}
        </div>
      )}
    </div>
  );
}
