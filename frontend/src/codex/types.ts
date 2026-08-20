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

/** One of the viewer's characters' knowledge of an entry. */
export interface CodexKnownBy {
  roster_entry_id: number;
  character_name: string;
  status: 'known' | 'uncovered';
  research_progress: number;
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
  /** Best status across the viewer's selected characters. */
  knowledge_status: 'known' | 'uncovered' | null;
  /** Per-character breakdown of the viewer's characters that know this entry. */
  known_by: CodexKnownBy[];
  art_url: string | null;
  /** Name of the culture whose take this entry is; null for canon entries. */
  perspective_of: string | null;
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
