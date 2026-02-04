export interface CodexCategory {
  id: number;
  name: string;
  description: string;
  display_order: number;
}

export interface CodexSubject {
  id: number;
  name: string;
  description: string;
  display_order: number;
  category: number;
  category_name: string;
  parent: number | null;
  parent_name: string | null;
  path: string[];
}

export interface CodexSubjectTreeNode {
  id: number;
  name: string;
  has_children: boolean;
  entry_count: number;
}

export interface CodexCategoryTree {
  id: number;
  name: string;
  description: string;
  subjects: CodexSubjectTreeNode[];
}

export interface CodexEntryListItem {
  id: number;
  name: string;
  summary: string;
  is_public: boolean;
  subject: number;
  subject_name: string;
  subject_path: string[];
  display_order: number;
  knowledge_status: 'known' | 'uncovered' | null;
}

export interface CodexEntryDetail extends CodexEntryListItem {
  content: string | null;
  learn_threshold: number;
  research_progress: number | null;
}
