import { useRef, useState, type DragEvent } from "react";
import { ErrorState, LoadingState } from "./States";

interface UploadPanelProps {
  isBusy: boolean;
  error: string | null;
  onUpload: (file: File) => void;
  onOpenDocument: (documentId: string) => void;
}

const ACCEPTED_TYPES = ".txt,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadPanel({ isBusy, error, onUpload, onOpenDocument }: UploadPanelProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const chooseFile = (file?: File) => {
    if (file) setSelectedFile(file);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    chooseFile(event.dataTransfer.files[0]);
  };

  return (
    <section className="upload-layout" aria-label="Document intake">
      <div className="upload-copy">
        <span className="eyebrow">Grounded decision intelligence</span>
        <h1>See what your document <em>isn’t</em> telling you.</h1>
        <p>
          Upload a decision document and surface hidden risks, assumptions, biases,
          missing voices, and hard questions—grounded in the source.
        </p>
        <div className="trust-row" aria-label="Product capabilities">
          <span>Source-aware analysis</span>
          <span>Six specialist agents</span>
          <span>Private backend processing</span>
        </div>
      </div>

      <div className="upload-card">
        <div className="card-heading">
          <div>
            <span className="step-number">01</span>
            <h2>Choose a document</h2>
          </div>
          <span className="secure-label">Processed locally</span>
        </div>

        <div
          className={`drop-zone${selectedFile ? " has-file" : ""}`}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
          }}
          role="button"
          tabIndex={0}
        >
          <input
            ref={inputRef}
            className="visually-hidden"
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={(event) => chooseFile(event.target.files?.[0])}
            aria-label="Select a document"
          />
          <span className="upload-glyph" aria-hidden="true">↗</span>
          {selectedFile ? (
            <>
              <strong>{selectedFile.name}</strong>
              <span>{formatBytes(selectedFile.size)} · Ready to upload</span>
            </>
          ) : (
            <>
              <strong>Drop your document here</strong>
              <span>or click to browse</span>
            </>
          )}
        </div>

        <p className="format-note">PDF, DOCX, PPTX, TXT, PNG, JPG or WEBP · up to 50 MB</p>
        <button
          className="button button-primary button-full"
          disabled={!selectedFile || isBusy}
          onClick={() => selectedFile && onUpload(selectedFile)}
        >
          Upload and process <span aria-hidden="true">→</span>
        </button>

        <div className="divider"><span>or resume a document</span></div>
        <form
          className="document-id-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (documentId.trim()) onOpenDocument(documentId.trim());
          }}
        >
          <label htmlFor="document-id">Document ID</label>
          <div>
            <input
              id="document-id"
              value={documentId}
              onChange={(event) => setDocumentId(event.target.value)}
              placeholder="doc_…"
              disabled={isBusy}
            />
            <button className="button button-secondary" disabled={!documentId.trim() || isBusy}>Open</button>
          </div>
        </form>

        {isBusy && (
          <LoadingState
            title={selectedFile ? "Uploading and processing" : "Opening document"}
            detail="The backend is extracting text and, when configured, analyzing visual evidence."
          />
        )}
        {error && !isBusy && <ErrorState message={error} />}
      </div>
    </section>
  );
}
