import { afterEach, describe, expect, it, vi } from "vitest";
import { analyzeDocument, API_TIMEOUT_MS, clearConversation, compareDocumentVersions, createConversation, getConversation, getDocument, getKnowledgeGraph, getVersionHistory, sendConversationMessage, uploadDocument, uploadDocumentVersion } from "./api";
import { graphFixture } from "../test/fixtures";

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
  it("uses explicit version and comparison endpoints", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ version_group_id: null, versions: [{ document_id: "doc_1", version_number: 1, filename: "v1.txt", file_type: "txt", created_at: "2026-09-01T00:00:00Z" }] }))
      .mockResolvedValueOnce(jsonResponse({ success: true, document_id: "doc_2", filename: "v2.txt", file_type: "txt", status: "processed", metadata: {}, warnings: [], version_group_id: "vg_1", version_number: 2, previous_document_id: "doc_1", created_at: "2026-09-01T00:00:00Z" }))
      .mockResolvedValueOnce(jsonResponse({
        old_document_id: "doc_1", new_document_id: "doc_2", summary: "Changed", structural_diff: {},
        new_risks: [], resolved_risks: [], persistent_risks: [], new_assumptions: [], resolved_assumptions: [], persistent_assumptions: [],
        new_biases: [], resolved_biases: [], persistent_biases: [], new_missing_perspectives: [], resolved_missing_perspectives: [], persistent_missing_perspectives: [],
        new_questions: [], resolved_questions: [], persistent_questions: [], recommendation_progress: [], meaningful_additions: [], meaningful_removals: [], regressions: [],
      }));
    vi.stubGlobal("fetch", fetchMock);

    await getVersionHistory("doc_1");
    await uploadDocumentVersion("doc_1", new File(["two"], "v2.txt"), "Review", "Notes");
    await compareDocumentVersions("doc_1", "doc_2");

    const historyCall = fetchMock.mock.calls.at(0)!;
    const uploadCall = fetchMock.mock.calls.at(1)!;
    const comparisonCall = fetchMock.mock.calls.at(2)!;
    expect(historyCall[0]).toMatch(/doc_1\/versions$/);
    expect((uploadCall[1] as RequestInit).body).toBeInstanceOf(FormData);
    expect(comparisonCall[0]).toMatch(/documents\/compare$/);
    expect((comparisonCall[1] as RequestInit).body).toBe(JSON.stringify({ old_document_id: "doc_1", new_document_id: "doc_2" }));
  });

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

  it("loads an explicitly scoped knowledge graph", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...graphFixture, scope: "series" }));
    vi.stubGlobal("fetch", fetchMock);

    const graph = await getKnowledgeGraph("doc id/1", "series");

    expect(graph.nodes).toHaveLength(5);
    expect(fetchMock.mock.calls[0]![0]).toMatch(/documents\/doc%20id%2F1\/graph\?scope=series$/);
  });

  it("rejects malformed graph relationships", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      ...graphFixture,
      edges: [{ type: "supports" }],
    })));

    await expect(getKnowledgeGraph("doc_123")).rejects.toThrow("invalid graph relationship");
  });

  it("uses document-scoped conversation endpoints", async () => {
    const conversation = {
      conversation_id: "conv_1", document_id: "doc_1", scope: "document",
      version_group_id: null, created_at: "now", updated_at: "now", messages: [],
    };
    const message = { message_id: "msg_1", role: "assistant", content: "Answer", created_at: "now" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(conversation, 201))
      .mockResolvedValueOnce(jsonResponse(conversation))
      .mockResolvedValueOnce(jsonResponse({ conversation_id: "conv_1", message, conversation: { ...conversation, messages: [message] } }))
      .mockResolvedValueOnce(jsonResponse(conversation));
    vi.stubGlobal("fetch", fetchMock);

    await createConversation("doc_1", "document");
    await getConversation("doc_1", "conv_1");
    const sent = await sendConversationMessage("doc_1", "conv_1", "Question");
    await clearConversation("doc_1", "conv_1");

    expect(sent.message.sources).toEqual([]);
    expect(sent.message.metadata).toEqual({});
    expect(fetchMock.mock.calls[0]![0]).toMatch(/doc_1\/conversations$/);
    expect((fetchMock.mock.calls[0]![1] as RequestInit).body).toBe(JSON.stringify({ scope: "document" }));
    expect(fetchMock.mock.calls[2]![0]).toMatch(/conv_1\/messages$/);
    expect((fetchMock.mock.calls[3]![1] as RequestInit).method).toBe("DELETE");
  });

  it("rejects a malformed conversation message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({
      conversation_id: "conv_1", document_id: "doc_1", scope: "document",
      created_at: "now", updated_at: "now", messages: [{ role: "assistant", content: "Missing ID" }],
    })));
    await expect(getConversation("doc_1", "conv_1")).rejects.toThrow("invalid conversation message");
  });
});
