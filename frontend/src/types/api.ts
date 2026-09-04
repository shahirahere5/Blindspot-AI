export type FileType = "pdf" | "pptx" | "docx" | "txt" | "image";
export type DocumentStatus =
  | "processed"
  | "requires_multimodal_processing"
  | "pending_multimodal_analysis"
  | "failed";
export type ContentBlockType = "page" | "slide" | "paragraph" | "table" | "text" | "image";
export type Severity = "low" | "medium" | "high" | "critical";
export type Priority = Severity;
export type Confidence = "low" | "medium" | "high";

export interface ContentBlock {
  type: ContentBlockType;
  location: number;
  text: string;
  extra: Record<string, unknown>;
}

export interface NormalizedDocument {
  document_id: string;
  filename: string;
  file_type: FileType;
  status: DocumentStatus;
  content: ContentBlock[];
  metadata: Record<string, unknown>;
  warnings: string[];
}

export interface UploadResponse {
  success: boolean;
  document_id: string;
  filename: string;
  file_type: FileType;
  status: DocumentStatus;
  metadata: Record<string, unknown>;
  warnings: string[];
}

export interface VersionEntry {
  document_id: string;
  version_number: number;
  filename: string;
  file_type: FileType;
  status: DocumentStatus;
  created_at: string;
  previous_document_id: string | null;
  label: string | null;
  notes: string | null;
}

export interface VersionHistory {
  version_group_id: string | null;
  versions: VersionEntry[];
}

export interface VersionedUploadResponse extends UploadResponse {
  version_group_id: string;
  version_number: number;
  previous_document_id: string;
  label: string | null;
  notes: string | null;
  created_at: string;
}

export type RecommendationProgressStatus =
  | "addressed" | "partially_addressed" | "not_addressed"
  | "no_longer_applicable" | "uncertain";

export interface ComparisonFinding {
  title: string;
  description: string;
  old_evidence: string;
  new_evidence: string;
  old_source_locations: number[];
  new_source_locations: number[];
}

export interface RecommendationProgress extends ComparisonFinding {
  progress_status: RecommendationProgressStatus;
}

export interface StructuralDiff {
  old_content_blocks: number;
  new_content_blocks: number;
  unchanged_blocks: number;
  added_blocks: number;
  removed_blocks: number;
  added_snippets: string[];
  removed_snippets: string[];
}

export interface ComparisonReport {
  old_document_id: string;
  new_document_id: string;
  version_group_id: string;
  old_version_number: number;
  new_version_number: number;
  status: "completed";
  summary: string;
  overall_change_assessment: string;
  new_risks: ComparisonFinding[];
  resolved_risks: ComparisonFinding[];
  persistent_risks: ComparisonFinding[];
  new_assumptions: ComparisonFinding[];
  resolved_assumptions: ComparisonFinding[];
  persistent_assumptions: ComparisonFinding[];
  new_biases: ComparisonFinding[];
  resolved_biases: ComparisonFinding[];
  persistent_biases: ComparisonFinding[];
  new_missing_perspectives: ComparisonFinding[];
  resolved_missing_perspectives: ComparisonFinding[];
  persistent_missing_perspectives: ComparisonFinding[];
  new_questions: ComparisonFinding[];
  resolved_questions: ComparisonFinding[];
  persistent_questions: ComparisonFinding[];
  recommendation_progress: RecommendationProgress[];
  meaningful_additions: ComparisonFinding[];
  meaningful_removals: ComparisonFinding[];
  regressions: ComparisonFinding[];
  structural_diff: StructuralDiff;
  metadata: Record<string, unknown>;
}

export interface Risk {
  title: string;
  description: string;
  severity: Severity;
  evidence: string;
  source_locations: number[];
  recommendation: string;
}

export interface Assumption {
  title: string;
  description: string;
  confidence: Confidence;
  evidence: string;
  source_locations: number[];
  why_it_matters: string;
}

export interface Bias {
  title: string;
  description: string;
  evidence: string;
  source_locations: number[];
  recommendation: string;
}

export interface MissingPerspective {
  perspective: string;
  description: string;
  why_it_matters: string;
  questions_to_consider: string[];
}

export interface UnansweredQuestion {
  question: string;
  importance: Priority;
  reason: string;
}

export interface Recommendation {
  priority: Priority;
  title: string;
  description: string;
}

export interface AnalysisReport {
  document_id: string;
  status: "completed" | "failed";
  summary: string;
  overall_assessment: string;
  risks: Risk[];
  assumptions: Assumption[];
  biases: Bias[];
  missing_perspectives: MissingPerspective[];
  unanswered_questions: UnansweredQuestion[];
  recommendations: Recommendation[];
  metadata: Record<string, unknown>;
}

export type AgentRole = "optimist" | "skeptic" | "security" | "financial" | "ethics" | "legal";

export interface AgentFinding extends Risk {}

export interface AgentAnalysis {
  agent: AgentRole;
  role: string;
  status: "succeeded" | "failed";
  error: string | null;
  summary: string;
  findings: AgentFinding[];
  assumptions: Assumption[];
  questions: UnansweredQuestion[];
  confidence: Confidence;
  metadata: Record<string, unknown>;
}

export interface DebateResult {
  document_id: string;
  status: "completed" | "failed";
  agent_analyses: AgentAnalysis[];
  agreements: string[];
  disagreements: string[];
  final_blind_spots: string[];
  final_risks: Risk[];
  final_assumptions: Assumption[];
  final_biases: Bias[];
  missing_perspectives: MissingPerspective[];
  unanswered_questions: UnansweredQuestion[];
  recommendations: Recommendation[];
  overall_assessment: string;
  metadata: Record<string, unknown>;
}
