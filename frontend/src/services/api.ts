import type {
  AnalysisReport,
  DebateResult,
  NormalizedDocument,
  UploadResponse,
} from "../types/api";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = (configuredBaseUrl || "http://127.0.0.1:8000").replace(/\/$/, "");
const configuredTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS);
export const API_TIMEOUT_MS = Number.isFinite(configuredTimeout) && configuredTimeout > 0
  ? configuredTimeout
  : 180_000;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | null = null,
    public readonly code: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatValidationDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;

  const messages = detail.flatMap((item) => {
    if (!isRecord(item) || typeof item.msg !== "string") return [];
    return [item.msg];
  });
  return messages.length > 0 ? messages.join(" ") : null;
}

function defaultMessage(status: number): string {
  if (status === 400) return "The request could not be completed. Check the document and try again.";
  if (status === 404) return "That document could not be found.";
  if (status === 413) return "This document is too large to analyze with the current backend settings.";
  if (status === 422) return "The backend could not process the response. Please try again.";
  if (status === 429) return "The AI service is busy. Wait a moment, then retry.";
  if (status === 502 || status === 504) return "The AI provider is temporarily unavailable. Please retry.";
  if (status >= 500) return "The backend encountered an error. Please try again.";
  return "The request failed. Please try again.";
}

const SAFE_SERVER_DETAILS = [
  /^AI (analysis|debate) is unavailable because the server is not configured\.$/,
  /^AI (analysis|debate) is temporarily unavailable\. Please try again\.$/,
  /^The AI provider rejected the server credentials\.$/,
  /^The AI service rate limit was reached\. Please wait and try again\.$/,
  /^The AI service is temporarily unavailable\. Please try again shortly\.$/,
  /^The AI service timed out\. Please try again\.$/,
  /^The configured AI model is currently unavailable\.$/,
  /^The AI service returned an invalid response\. Please try again\.$/,
  /^Document (indexing|retrieval) is temporarily unavailable\.$/,
];

function safeErrorDetail(status: number, detail: string | null): string | null {
  if (detail === null || status < 500) return detail;
  return SAFE_SERVER_DETAILS.some((pattern) => pattern.test(detail)) ? detail : null;
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new ApiError(
      response.ok ? "The backend returned an unexpected response." : defaultMessage(response.status),
      response.status,
    );
  }

  try {
    return await response.json();
  } catch {
    throw new ApiError("The backend returned malformed JSON.", response.status);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, signal: controller.signal });
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError("The request timed out. Please try again.");
    }
    throw new ApiError("Cannot reach the Blind Spot AI backend. Confirm that it is running.");
  } finally {
    window.clearTimeout(timeoutId);
  }

  const body = await readJson(response);
  if (!response.ok) {
    const rawDetail = isRecord(body) ? formatValidationDetail(body.detail) : null;
    const detail = safeErrorDetail(response.status, rawDetail);
    const code = isRecord(body) && typeof body.error === "string" ? body.error : null;
    throw new ApiError(detail ?? defaultMessage(response.status), response.status, code);
  }

  if (!isRecord(body)) {
    throw new ApiError("The backend returned an unexpected response.", response.status);
  }
  return body as T;
}

function ensureDocumentId(value: Record<string, unknown>): void {
  if (typeof value.document_id !== "string" || value.document_id.length === 0) {
    throw new ApiError("The backend response did not include a valid document ID.");
  }
}

function ensureArrays(value: Record<string, unknown>, keys: readonly string[]): void {
  for (const key of keys) {
    if (!Array.isArray(value[key])) {
      throw new ApiError(`The backend response contained an invalid '${key}' field.`);
    }
  }
}

function validateUpload(value: UploadResponse): UploadResponse {
  const record = value as unknown as Record<string, unknown>;
  ensureDocumentId(record);
  ensureArrays(record, ["warnings"]);
  if (typeof record.filename !== "string" || typeof record.status !== "string") {
    throw new ApiError("The backend returned an invalid upload response.");
  }
  return value;
}

function validateDocument(value: NormalizedDocument): NormalizedDocument {
  const record = value as unknown as Record<string, unknown>;
  ensureDocumentId(record);
  ensureArrays(record, ["content", "warnings"]);
  if (!isRecord(record.metadata) || typeof record.filename !== "string") {
    throw new ApiError("The backend returned an invalid document response.");
  }
  for (const block of value.content) {
    if (!isRecord(block) || typeof block.type !== "string" || typeof block.location !== "number" || typeof block.text !== "string") {
      throw new ApiError("The backend returned invalid document content.");
    }
  }
  return value;
}

function ensureSourceLocations(items: unknown[]): void {
  for (const item of items) {
    if (!isRecord(item)) throw new ApiError("The backend returned an invalid finding.");
    if ("source_locations" in item && !Array.isArray(item.source_locations)) {
      throw new ApiError("The backend returned invalid source references.");
    }
  }
}

function validateAnalysis(value: AnalysisReport): AnalysisReport {
  const record = value as unknown as Record<string, unknown>;
  ensureDocumentId(record);
  ensureArrays(record, ["risks", "assumptions", "biases", "missing_perspectives", "unanswered_questions", "recommendations"]);
  ensureSourceLocations([...value.risks, ...value.assumptions, ...value.biases]);
  if (!isRecord(record.metadata) || typeof record.summary !== "string" || typeof record.overall_assessment !== "string") {
    throw new ApiError("The backend returned an invalid analysis response.");
  }
  return value;
}

function validateDebate(value: DebateResult): DebateResult {
  const record = value as unknown as Record<string, unknown>;
  ensureDocumentId(record);
  ensureArrays(record, [
    "agent_analyses", "agreements", "disagreements", "final_blind_spots",
    "final_risks", "final_assumptions", "final_biases", "missing_perspectives",
    "unanswered_questions", "recommendations",
  ]);
  ensureSourceLocations([...value.final_risks, ...value.final_assumptions, ...value.final_biases]);
  for (const agent of value.agent_analyses) {
    if (!isRecord(agent) || !Array.isArray(agent.findings) || !Array.isArray(agent.assumptions) || !Array.isArray(agent.questions)) {
      throw new ApiError("The backend returned an invalid agent analysis.");
    }
    ensureSourceLocations([...agent.findings, ...agent.assumptions]);
  }
  if (!isRecord(record.metadata) || typeof record.overall_assessment !== "string") {
    throw new ApiError("The backend returned an invalid debate response.");
  }
  return value;
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return validateUpload(await request<UploadResponse>("/api/documents/upload", {
    method: "POST",
    body: formData,
  }));
}

export async function getDocument(documentId: string): Promise<NormalizedDocument> {
  return validateDocument(await request<NormalizedDocument>(
    `/api/documents/${encodeURIComponent(documentId)}`,
  ));
}

export async function analyzeDocument(documentId: string): Promise<AnalysisReport> {
  return validateAnalysis(await request<AnalysisReport>(
    `/api/documents/${encodeURIComponent(documentId)}/analyze`,
    { method: "POST" },
  ));
}

export async function debateDocument(documentId: string): Promise<DebateResult> {
  return validateDebate(await request<DebateResult>(
    `/api/documents/${encodeURIComponent(documentId)}/debate`,
    { method: "POST" },
  ));
}
