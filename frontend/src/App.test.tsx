import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { ApiError } from "./services/api";
import { analysisFixture, debateFixture, documentFixture, visualDocumentFixture } from "./test/fixtures";

const apiMocks = vi.hoisted(() => ({
  uploadDocument: vi.fn(),
  getDocument: vi.fn(),
  analyzeDocument: vi.fn(),
  debateDocument: vi.fn(),
  getVersionHistory: vi.fn(),
  uploadDocumentVersion: vi.fn(),
  compareDocumentVersions: vi.fn(),
}));

vi.mock("./services/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("./services/api")>();
  return { ...original, ...apiMocks };
});

async function openFixtureDocument() {
  const user = userEvent.setup();
  apiMocks.getDocument.mockResolvedValue(documentFixture);
  await user.type(screen.getByLabelText("Document ID"), documentFixture.document_id);
  await user.click(screen.getByRole("button", { name: "Open" }));
  await screen.findByText("Revenue depends on one customer.");
  return user;
}

beforeEach(() => {
  Object.values(apiMocks).forEach((mock) => mock.mockReset());
});

describe("Blind Spot AI workspace", () => {
  it("shows explicit history, uploads a successor, and renders side-labeled comparison evidence", async () => {
    const versions = [
      { document_id: documentFixture.document_id, version_number: 1, filename: "strategy.pdf", file_type: "pdf", status: "processed", created_at: "2026-09-01T10:00:00Z", previous_document_id: null, label: null, notes: null },
      { document_id: "doc_v2", version_number: 2, filename: "strategy-v2.pdf", file_type: "pdf", status: "processed", created_at: "2026-09-02T10:00:00Z", previous_document_id: documentFixture.document_id, label: "Board review", notes: "Updated assumptions" },
    ] as const;
    apiMocks.getVersionHistory.mockResolvedValue({ version_group_id: "vg_test", versions });
    apiMocks.compareDocumentVersions.mockResolvedValue({
      old_document_id: documentFixture.document_id, new_document_id: "doc_v2", version_group_id: "vg_test",
      old_version_number: 1, new_version_number: 2, status: "completed", summary: "The revision improves validation.",
      overall_change_assessment: "Risk is reduced, with one new dependency.",
      new_risks: [{ title: "Pilot dependency", description: "The pilot is now critical.", old_evidence: "", new_evidence: "Pilot required", old_source_locations: [], new_source_locations: [4] }],
      resolved_risks: [{ title: "Security gap", description: "An audit was added.", old_evidence: "No audit", new_evidence: "Audit complete", old_source_locations: [2], new_source_locations: [3] }],
      persistent_risks: [{ title: "Supplier reliance", description: "Still unresolved.", old_evidence: "One supplier", new_evidence: "One supplier", old_source_locations: [1], new_source_locations: [2] }], new_assumptions: [], resolved_assumptions: [], persistent_assumptions: [],
      new_biases: [], resolved_biases: [], persistent_biases: [], new_missing_perspectives: [], resolved_missing_perspectives: [],
      persistent_missing_perspectives: [], new_questions: [], resolved_questions: [], persistent_questions: [], recommendation_progress: [{ title: "Run audit", description: "Completed", progress_status: "addressed", old_evidence: "Audit recommended", new_evidence: "Audit complete", old_source_locations: [2], new_source_locations: [3] }],
      meaningful_additions: [], meaningful_removals: [], regressions: [],
      structural_diff: { old_content_blocks: 2, new_content_blocks: 4, unchanged_blocks: 2, added_blocks: 2, removed_blocks: 0, added_snippets: [], removed_snippets: [] },
      metadata: {},
    });
    render(<App />);
    const user = await openFixtureDocument();
    await user.click(screen.getByRole("button", { name: /versions/i }));
    expect((await screen.findAllByText(/Board review/)).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Compare blind spots" }));
    expect(await screen.findByText("Pilot dependency")).toBeInTheDocument();
    expect(screen.getByText("Security gap")).toBeInTheDocument();
    expect(screen.getByText("Supplier reliance")).toBeInTheDocument();
    expect(screen.getByText("Run audit")).toBeInTheDocument();
    expect(screen.getByText("V2 · Page 4")).toBeInTheDocument();
    expect(apiMocks.compareDocumentVersions).toHaveBeenCalledWith(documentFixture.document_id, "doc_v2");
  });

  it("shows one-version state and safe comparison loading/failure", async () => {
    const first = { document_id: documentFixture.document_id, version_number: 1, filename: "strategy.pdf", file_type: "pdf", status: "processed", created_at: "2026-09-01T10:00:00Z", previous_document_id: null, label: null, notes: null };
    const second = { ...first, document_id: "doc_v2", version_number: 2, filename: "strategy-v2.pdf", previous_document_id: first.document_id };
    apiMocks.getVersionHistory
      .mockResolvedValueOnce({ version_group_id: null, versions: [first] })
      .mockResolvedValueOnce({ version_group_id: "vg_test", versions: [first, second] });
    render(<App />);
    const user = await openFixtureDocument();
    await user.click(screen.getByRole("button", { name: /versions/i }));
    await screen.findByText("Upload after V1");
    expect(screen.queryByRole("button", { name: "Compare blind spots" })).not.toBeInTheDocument();

    apiMocks.uploadDocumentVersion.mockResolvedValue({ document_id: second.document_id });
    const revision = new File(["revision"], "strategy-v2.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Revision file"), revision);
    const uploadButton = screen.getByRole("button", { name: "Upload after V1" });
    await waitFor(() => expect(uploadButton).toBeEnabled());
    fireEvent.submit(uploadButton.closest("form")!);
    await waitFor(() => expect(apiMocks.uploadDocumentVersion).toHaveBeenCalledWith(first.document_id, revision, "", ""));
    await waitFor(() => expect(apiMocks.getVersionHistory).toHaveBeenCalledTimes(2));
    let rejectComparison: ((reason: Error) => void) | undefined;
    apiMocks.compareDocumentVersions.mockImplementation(() => new Promise((_resolve, reject) => { rejectComparison = reject; }));
    await user.click(await screen.findByRole("button", { name: "Compare blind spots" }));
    expect(screen.getByRole("button", { name: "Comparing…" })).toBeDisabled();
    rejectComparison?.(new ApiError("AI comparison is temporarily unavailable. Please try again.", 502));
    expect(await screen.findByRole("alert")).toHaveTextContent("AI comparison is temporarily unavailable");
  });

  it("shows real upload progress and opens the normalized document", async () => {
    const user = userEvent.setup();
    let finishUpload: ((value: { document_id: string }) => void) | undefined;
    apiMocks.uploadDocument.mockImplementation(() => new Promise((resolve) => { finishUpload = resolve; }));
    apiMocks.getDocument.mockResolvedValue(documentFixture);
    render(<App />);

    const file = new File(["strategy"], "strategy.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Select a document"), file);
    await user.click(screen.getByRole("button", { name: /Upload and process/ }));
    expect(screen.getByRole("status")).toHaveTextContent("Uploading and processing");

    finishUpload?.({ document_id: documentFixture.document_id });
    await screen.findByText("Revenue depends on one customer.");
    expect(apiMocks.getDocument).toHaveBeenCalledWith(documentFixture.document_id);
  });

  it("shows a safe backend error in the intake flow", async () => {
    const user = userEvent.setup();
    apiMocks.getDocument.mockRejectedValue(new ApiError("That document could not be found.", 404));
    render(<App />);

    await user.type(screen.getByLabelText("Document ID"), "doc_missing");
    await user.click(screen.getByRole("button", { name: "Open" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("That document could not be found.");
  });

  it("shows an upload-specific failure without leaving the intake screen", async () => {
    const user = userEvent.setup();
    apiMocks.uploadDocument.mockRejectedValue(new ApiError("Unsupported file type.", 400));
    render(<App />);

    const file = new File(["invalid"], "invalid.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Select a document"), file);
    await user.click(screen.getByRole("button", { name: /Upload and process/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unsupported file type.");
    expect(screen.getByText("Choose a document")).toBeInTheDocument();
  });

  it("uploads an image and displays completed visual evidence", async () => {
    const user = userEvent.setup();
    apiMocks.uploadDocument.mockResolvedValue({
      success: true,
      document_id: visualDocumentFixture.document_id,
      filename: visualDocumentFixture.filename,
      file_type: "image",
      status: "processed",
      metadata: visualDocumentFixture.metadata,
      warnings: [],
    });
    apiMocks.getDocument.mockResolvedValue(visualDocumentFixture);
    render(<App />);

    const image = new File(["image"], "strategy-chart.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("Select a document"), image);
    await user.click(screen.getByRole("button", { name: /Upload and process/ }));

    expect(await screen.findByText("Visual analysis complete")).toBeInTheDocument();
    expect(screen.getByText(/Revenue rises while operating margin falls/)).toBeInTheDocument();
    expect(apiMocks.uploadDocument).toHaveBeenCalledWith(image);
  });

  it("shows a safe unavailable state for visual processing", async () => {
    const unavailable = {
      ...visualDocumentFixture,
      status: "pending_multimodal_analysis" as const,
      content: [],
      metadata: { ...visualDocumentFixture.metadata, multimodal: { status: "unavailable" } },
      warnings: ["Visual analysis is currently unavailable."],
    };
    apiMocks.getDocument.mockResolvedValue(unavailable);
    render(<App />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Document ID"), unavailable.document_id);
    await user.click(screen.getByRole("button", { name: "Open" }));

    expect(await screen.findByText("Visual analysis unavailable")).toBeInTheDocument();
    expect(screen.getByText("Visual analysis is currently unavailable.")).toBeInTheDocument();
    expect(screen.queryByText(/API_KEY|\.env|AuthenticationError/)).not.toBeInTheDocument();
  });

  it("navigates to analysis and renders grounded findings", async () => {
    render(<App />);
    const user = await openFixtureDocument();
    apiMocks.analyzeDocument.mockResolvedValue(analysisFixture);

    await user.click(screen.getByRole("button", { name: /analysis/i }));
    expect(screen.getByText("Reveal the first layer of blind spots")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    expect(await screen.findByText("Customer concentration")).toBeInTheDocument();
    expect(screen.getByText("The strategy has a promising market but concentrated revenue exposure.")).toBeInTheDocument();
    expect(screen.getByText("Page 2")).toBeInTheDocument();
    expect(screen.getByText("RAG grounded")).toBeInTheDocument();
  });

  it("shows the analysis loading state while the backend request is pending", async () => {
    render(<App />);
    const user = await openFixtureDocument();
    let finishAnalysis: ((value: typeof analysisFixture) => void) | undefined;
    apiMocks.analyzeDocument.mockImplementation(() => new Promise((resolve) => { finishAnalysis = resolve; }));

    await user.click(screen.getByRole("button", { name: /analysis/i }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(screen.getByRole("status")).toHaveTextContent("Analyzing blind spots");

    finishAnalysis?.(analysisFixture);
    expect(await screen.findByText("Customer concentration")).toBeInTheDocument();
  });

  it("renders agent output and moderator synthesis from the debate response", async () => {
    render(<App />);
    const user = await openFixtureDocument();
    apiMocks.debateDocument.mockResolvedValue(debateFixture);

    await user.click(screen.getByRole("button", { name: /Agent debate/i }));
    await user.click(screen.getByRole("button", { name: "Start agent debate" }));

    expect(await screen.findByText("Where the panel landed")).toBeInTheDocument();
    expect(screen.getByText("Skeptic")).toBeInTheDocument();
    expect(screen.getByText("Unvalidated growth")).toBeInTheDocument();
    expect(screen.getAllByText("Page 2").length).toBeGreaterThan(0);
    expect(screen.getByText("Demand validation is essential.")).toBeInTheDocument();
  });

  it("shows analysis retry state when the AI request fails", async () => {
    render(<App />);
    const user = await openFixtureDocument();
    apiMocks.analyzeDocument.mockRejectedValue(new ApiError("The AI service is busy. Wait a moment, then retry.", 429));

    await user.click(screen.getByRole("button", { name: /analysis/i }));
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The AI service is busy");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.analyzeDocument).toHaveBeenCalledOnce());
  });
});
