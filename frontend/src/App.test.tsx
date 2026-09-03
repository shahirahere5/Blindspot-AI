import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { ApiError } from "./services/api";
import { analysisFixture, debateFixture, documentFixture } from "./test/fixtures";

const apiMocks = vi.hoisted(() => ({
  uploadDocument: vi.fn(),
  getDocument: vi.fn(),
  analyzeDocument: vi.fn(),
  debateDocument: vi.fn(),
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
