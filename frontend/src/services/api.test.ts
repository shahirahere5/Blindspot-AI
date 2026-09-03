import { afterEach, describe, expect, it, vi } from "vitest";
import { analyzeDocument, API_TIMEOUT_MS, getDocument, uploadDocument } from "./api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("API service", () => {
  it("uploads a multipart file through the centralized endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      success: true,
      document_id: "doc_123",
      filename: "plan.txt",
      file_type: "txt",
      status: "processed",
      metadata: {},
      warnings: [],
    }));
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["hello"], "plan.txt", { type: "text/plain" });
    const result = await uploadDocument(file);

    expect(result.document_id).toBe("doc_123");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url.endsWith("/api/documents/upload")).toBe(true);
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("preserves backend error detail and status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Rate limit reached." }, 429)));

    await expect(analyzeDocument("doc_123")).rejects.toMatchObject({
      message: "Rate limit reached.",
      status: 429,
    });
  });

  it("turns network failures into a safe actionable message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network failed")));

    await expect(getDocument("doc_123")).rejects.toThrow("Confirm that it is running");
  });

  it("does not expose unapproved internal details from server errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      detail: "GROQ_API_KEY is missing from C:\\private\\.env",
    }, 500)));

    await expect(analyzeDocument("doc_123")).rejects.toMatchObject({
      message: "The backend encountered an error. Please try again.",
      status: 500,
    });
  });

  it("aborts a request that exceeds the client timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_url, init: RequestInit) => (
      new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      })
    )));

    const rejection = expect(getDocument("doc_123")).rejects.toThrow("request timed out");
    await vi.advanceTimersByTimeAsync(API_TIMEOUT_MS);

    await rejection;
  });

  it("rejects a successful response without a document ID", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ content: [] })));

    await expect(getDocument("doc_123")).rejects.toThrow("valid document ID");
  });

  it("rejects an analysis response with malformed collection fields", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      document_id: "doc_123",
      summary: "Summary",
      overall_assessment: "Assessment",
      risks: null,
      assumptions: [],
      biases: [],
      missing_perspectives: [],
      unanswered_questions: [],
      recommendations: [],
      metadata: {},
    })));

    await expect(analyzeDocument("doc_123")).rejects.toThrow("invalid 'risks' field");
  });
});
