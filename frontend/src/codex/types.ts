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
  path: BreadcrumbSegment[];
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

export interface BreadcrumbSegment {
  type: 'category' | 'subject';
  id: number;
  name: string;
}

export interface CodexEntryListItem {
  id: number;
  name: string;
  summary: string;
  is_public: boolean;
  is_featured: boolean;
  featured_order: number | null;
  subject: number;
  subject_name: string;
  subject_path: BreadcrumbSegment[];
  display_order: number;
  knowledge_status: 'known' | 'uncovered' | null;
  art_url: string | null;
}

export interface CodexLinkRef {
  match_text: string;
  entry_id: number | null;
  display_text: string;
  accessible: boolean;
}

export interface CodexEntryDetail extends CodexEntryListItem {
  lore_content: string | null;
  mechanics_content: string | null;
  lore_links: CodexLinkRef[];
  mechanics_links: CodexLinkRef[];
  learn_threshold: number;
  research_progress: number | null;
}
