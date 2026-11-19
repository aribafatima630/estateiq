export type SourceName = "darglobal" | "wasalt";

export interface Citation {
  title: string;
  source: string;
  source_url: string;
  category: string;
}

export interface PropertyCard {
  id: string;
  title: string;
  source: string;
  location: string | null;
  city: string | null;
  price: number | null;
  currency: string | null;
  property_type: string | null;
  purpose: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  area_sqm: number | null;
  source_url: string;
}

export interface ProjectCard {
  id: string;
  title: string;
  location: string | null;
  property_type: string | null;
  summary: string;
  source_url: string;
  brands: string[];
}

export interface ComparisonRow {
  label: string;
  values: string[];
}

export interface ComparisonTable {
  columns: string[];
  rows: ComparisonRow[];
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  grounded: boolean;
  llm_used: boolean;
  citations: Citation[];
  properties: PropertyCard[];
  projects: ProjectCard[];
  comparison: ComparisonTable | null;
}

export interface SessionSummary {
  id: string;
  title: string | null;
  source_filter: string | null;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  payload?: ChatResponse | null;
}
