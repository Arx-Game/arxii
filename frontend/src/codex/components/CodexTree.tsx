import { useState } from 'react';
import { ChevronRight, ChevronDown, FileText, Folder, FolderOpen } from 'lucide-react';
import type { CodexCategoryTree, CodexSubjectTreeNode } from '../types';

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

  return (
    <div className="space-y-1">
      {categories.map((category) => (
        <CategoryNode
          key={category.id}
          category={category}
          expandedNodes={expandedNodes}
          toggleNode={toggleNode}
          onSelectSubject={onSelectSubject}
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
}

function CategoryNode({ category, expandedNodes, toggleNode, onSelectSubject }: CategoryNodeProps) {
  const nodeKey = category.name;
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
}

function SubjectNode({
  subject,
  parentKey,
  expandedNodes,
  toggleNode,
  onSelectSubject,
}: SubjectNodeProps) {
  const nodeKey = `${parentKey}/${subject.name}`;
  const isExpanded = expandedNodes.has(nodeKey);
  const hasChildren = subject.children.length > 0;

  return (
    <div>
      <div className="flex items-center">
        {hasChildren ? (
          <button onClick={() => toggleNode(nodeKey)} className="rounded p-0.5 hover:bg-accent">
            {isExpanded ? (
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
      {isExpanded && hasChildren && (
        <div className="ml-4">
          {subject.children.map((child) => (
            <SubjectNode
              key={child.id}
              subject={child}
              parentKey={nodeKey}
              expandedNodes={expandedNodes}
              toggleNode={toggleNode}
              onSelectSubject={onSelectSubject}
            />
          ))}
        </div>
      )}
    </div>
  );
}
