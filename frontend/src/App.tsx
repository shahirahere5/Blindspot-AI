import { useState } from "react";
import { AnalysisView } from "./components/AnalysisView";
import { DebateView } from "./components/DebateView";
import { DocumentView } from "./components/DocumentView";
import { UploadPanel } from "./components/UploadPanel";
import { VersionView } from "./components/VersionView";
import { GraphView } from "./components/GraphView";
import { ChatView } from "./components/ChatView";
import { analyzeDocument, ApiError, debateDocument, getDocument, uploadDocument } from "./services/api";
import type { AnalysisReport, DebateResult, NormalizedDocument } from "./types/api";

type Tab = "document" | "analysis" | "debate" | "versions" | "graph" | "chat";
type Operation = "upload" | "open" | "analysis" | "debate" | null;

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "An unexpected error occurred. Please try again.";
}

export default function App() {
  const [document, setDocument] = useState<NormalizedDocument | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null);
  const [debate, setDebate] = useState<DebateResult | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("document");
  const [operation, setOperation] = useState<Operation>(null);
  const [intakeError, setIntakeError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [debateError, setDebateError] = useState<string | null>(null);

  const openDocument = async (documentId: string) => {
    setOperation("open");
    setIntakeError(null);
    try {
      const loaded = await getDocument(documentId);
      setDocument(loaded);
      setAnalysis(null);
      setDebate(null);
      setActiveTab("document");
    } catch (error) {
      setIntakeError(errorMessage(error));
    } finally {
      setOperation(null);
    }
  };

  const handleUpload = async (file: File) => {
    setOperation("upload");
    setIntakeError(null);
    try {
      const uploaded = await uploadDocument(file);
      const loaded = await getDocument(uploaded.document_id);
      setDocument(loaded);
      setAnalysis(null);
      setDebate(null);
      setActiveTab("document");
    } catch (error) {
      setIntakeError(errorMessage(error));
    } finally {
      setOperation(null);
    }
  };

  const runAnalysis = async () => {
    if (!document) return;
    setOperation("analysis");
    setAnalysisError(null);
    try {
      setAnalysis(await analyzeDocument(document.document_id));
    } catch (error) {
      setAnalysisError(errorMessage(error));
    } finally {
      setOperation(null);
    }
  };

  const runDebate = async () => {
    if (!document) return;
    setOperation("debate");
    setDebateError(null);
    try {
      setDebate(await debateDocument(document.document_id));
    } catch (error) {
      setDebateError(errorMessage(error));
    } finally {
      setOperation(null);
    }
  };

  const startOver = () => {
    setDocument(null);
    setAnalysis(null);
    setDebate(null);
    setIntakeError(null);
    setAnalysisError(null);
    setDebateError(null);
    setActiveTab("document");
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={startOver} aria-label="Blind Spot AI home">
          <span className="brand-mark" aria-hidden="true"><i /><i /></span>
          <span>Blind Spot <strong>AI</strong></span>
        </button>
        <div className="topbar-meta"><span className="live-dot" />System ready</div>
      </header>

      <main>
        {!document ? (
          <UploadPanel
            isBusy={operation === "upload" || operation === "open"}
            error={intakeError}
            onUpload={handleUpload}
            onOpenDocument={openDocument}
          />
        ) : (
          <div className="workspace">
            <header className="workspace-header">
              <div className="document-identity">
                <span className="file-icon">{document.file_type.slice(0, 3).toUpperCase()}</span>
                <div><h1>{document.filename}</h1><p>{document.document_id}</p></div>
              </div>
              <button className="button button-secondary" onClick={startOver}>New document</button>
            </header>

            <nav className="tab-bar" aria-label="Document workspace">
              {(["document", "analysis", "debate", "versions", "graph", "chat"] as const).map((tab, index) => (
                <button
                  key={tab}
                  className={activeTab === tab ? "active" : ""}
                  onClick={() => setActiveTab(tab)}
                  aria-current={activeTab === tab ? "page" : undefined}
                >
                  <span>0{index + 1}</span>{tab === "debate" ? "Agent debate" : tab}
                  {tab === "analysis" && analysis && <i aria-label="Analysis complete" />}
                  {tab === "debate" && debate && <i aria-label="Debate complete" />}
                </button>
              ))}
            </nav>

            <div className="workspace-content">
              {activeTab === "document" && <DocumentView document={document} />}
              {activeTab === "analysis" && (
                <AnalysisView document={document} report={analysis} isLoading={operation === "analysis"} error={analysisError} onAnalyze={runAnalysis} />
              )}
              {activeTab === "debate" && (
                <DebateView document={document} debate={debate} isLoading={operation === "debate"} error={debateError} onDebate={runDebate} />
              )}
              {activeTab === "versions" && <VersionView document={document} />}
              {activeTab === "graph" && <GraphView document={document} />}
              {activeTab === "chat" && <ChatView document={document} />}
            </div>
          </div>
        )}
      </main>

      <footer><span>Blind Spot AI</span><span>Evidence first. Decisions clearer.</span></footer>
    </div>
  );
}
