export type FileType = "pdf" | "pptx" | "docx" | "txt" | "image";
export type DocumentStatus =
  | "processed"
  | "requires_multimodal_processing"
  | "pending_multimodal_analysis"
  | "failed";
export type ContentBlockType = "page" | "slide" | "paragraph" | "table" | "text";
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
