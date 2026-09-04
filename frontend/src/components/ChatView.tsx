import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError, clearConversation, createConversation, getConversation, sendConversationMessage,
} from "../services/api";
import {
  createVoiceSession, isSpeechOutputSupported, isVoiceInputSupported,
  speakText, stopSpeaking, type VoiceSession,
} from "../services/voice";
import type {
  Conversation, ConversationMessage, ConversationScope, ConversationSource, NormalizedDocument,
} from "../types/api";

const suggestions = [
  "What am I missing?",
  "What are the highest risks?",
  "Which assumptions need evidence?",
  "Which recommendations should I prioritize?",
  "What did the agents identify?",
  "What changed in the latest version?",
];

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Conversation is temporarily unavailable. Please try again.";
}

function sourceLabel(source: ConversationSource) {
  const version = source.version_number ? `V${source.version_number} · ` : "";
  const visual = source.visual_derived ? "Visual evidence · " : "";
  return `${version}${visual}${source.source_type.charAt(0).toUpperCase()}${source.source_type.slice(1)} ${source.source_location}`;
}

export function ChatView({ document }: { document: NormalizedDocument }) {
  const [scope, setScope] = useState<ConversationScope>("document");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voiceState, setVoiceState] = useState<"idle" | "listening" | "ready">("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const voiceSession = useRef<VoiceSession | null>(null);

  const storageKey = `blindspot-conversation:${document.document_id}:${scope}`;
  useEffect(() => {
    let active = true;
    const conversationId = sessionStorage.getItem(storageKey);
    setConversation(null); setError(null); setPendingUser(null);
    if (!conversationId) { setLoadingHistory(false); return () => { active = false; }; }
    setLoadingHistory(true);
    getConversation(document.document_id, conversationId)
      .then((value) => { if (active) setConversation(value); })
      .catch(() => { sessionStorage.removeItem(storageKey); })
      .finally(() => { if (active) setLoadingHistory(false); });
    return () => { active = false; voiceSession.current?.stop(); stopSpeaking(); };
  }, [document.document_id, storageKey]);

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;
    setSending(true); setPendingUser(content); setDraft(""); setError(null); setVoiceState("idle");
    try {
      let activeConversation = conversation;
      if (!activeConversation) {
        activeConversation = await createConversation(document.document_id, scope);
        sessionStorage.setItem(storageKey, activeConversation.conversation_id);
      }
      const result = await sendConversationMessage(
        document.document_id, activeConversation.conversation_id, content,
      );
      setConversation(result.conversation);
    } catch (caught) {
      setDraft(content);
      setError(errorMessage(caught));
    } finally {
      setPendingUser(null); setSending(false);
    }
  };

  const clear = async () => {
    setError(null); stopSpeaking(); setSpeakingId(null);
    if (!conversation) { setDraft(""); return; }
    try {
      setConversation(await clearConversation(document.document_id, conversation.conversation_id));
    } catch (caught) { setError(errorMessage(caught)); }
  };

  const listen = () => {
    setVoiceError(null);
    if (!isVoiceInputSupported()) {
      setVoiceError("Voice input isn't available in this browser. You can continue using text.");
      return;
    }
    const session = createVoiceSession({
      onResult: (transcript) => {
        if (transcript) { setDraft(transcript); setVoiceState("ready"); }
        else setVoiceError("No speech was detected. You can type your question instead.");
      },
      onError: (reason) => {
        setVoiceState("idle");
        setVoiceError(reason === "permission_denied"
          ? "Microphone permission was denied. You can continue using text."
          : reason === "no_speech" ? "No speech was detected. You can type your question instead."
            : "Voice recognition failed. You can continue using text.");
      },
      onEnd: () => setVoiceState((current) => current === "listening" ? "idle" : current),
    });
    voiceSession.current = session;
    try { session?.start(); setVoiceState("listening"); }
    catch { setVoiceState("idle"); setVoiceError("Voice recognition could not start. You can continue using text."); }
  };

  const speak = (message: ConversationMessage) => {
    if (speakingId === message.message_id) {
      stopSpeaking(); setSpeakingId(null); return;
    }
    if (!isSpeechOutputSupported()) {
      setVoiceError("Spoken output isn't available in this browser."); return;
    }
    setSpeakingId(message.message_id);
    speakText(message.content, () => setSpeakingId(null));
  };

  const messages = conversation?.messages ?? [];
  return <div className="view-stack chat-view">
    <section className="content-section chat-header">
      <div className="section-heading"><span className="eyebrow">Grounded conversation</span><h2>Ask Blind Spot AI</h2>
        <p>Answers use scoped document evidence and explicit graph relationships—not general web knowledge.</p></div>
      <div className="chat-scope"><span>Chatting with</span><strong>{scope === "series" ? `Version series · ${document.filename}` : document.filename}</strong>
        <div className="scope-toggle" aria-label="Conversation scope">
          <button className={scope === "document" ? "active" : ""} onClick={() => setScope("document")}>This document</button>
          <button className={scope === "series" ? "active" : ""} onClick={() => setScope("series")}>Version series</button>
        </div></div>
    </section>

    <section className="chat-panel">
      {loadingHistory && <div className="chat-status" role="status">Loading conversation…</div>}
      {!loadingHistory && messages.length === 0 && !pendingUser && <div className="chat-empty">
        <span className="eyebrow">Start with evidence</span><h3>What would you like to examine?</h3>
        <p>Ask about risks, assumptions, recommendations, sources, agents, or version changes.</p>
        <div className="suggested-questions">{suggestions.map((value) => <button key={value} onClick={() => setDraft(value)}>{value}</button>)}</div>
      </div>}
      <div className="message-list" aria-live="polite">
        {messages.map((message) => <article key={message.message_id} className={`chat-message ${message.role}`}>
          <div className="message-meta"><strong>{message.role === "user" ? "You" : "Blind Spot AI"}</strong>
            {message.role === "assistant" && <button onClick={() => speak(message)}>{speakingId === message.message_id ? "Stop" : "Speak"}</button>}</div>
          <p>{message.content}</p>
          {message.sources.length > 0 && <div className="chat-sources" aria-label="Answer sources">{message.sources.map((source) => <details key={source.source_id}>
            <summary>{sourceLabel(source)}</summary><p>{source.excerpt}</p></details>)}</div>}
          {message.related_findings.length > 0 && <div className="related-findings" aria-label="Related findings">{message.related_findings.map((item) => <span key={item.node_id}>{item.type.replaceAll("_", " ")} · {item.label}</span>)}</div>}
        </article>)}
        {pendingUser && <article className="chat-message user"><div className="message-meta"><strong>You</strong></div><p>{pendingUser}</p></article>}
        {sending && <div className="chat-status" role="status"><span className="spinner" />Finding grounded evidence…</div>}
      </div>
      {error && <div className="chat-error" role="alert">{error}</div>}
      {voiceError && <div className="voice-error" role="alert">{voiceError}</div>}
      <form className="chat-composer" onSubmit={send}>
        <label htmlFor="chat-message">Ask about this {scope === "series" ? "version series" : "document"}</label>
        <textarea id="chat-message" value={draft} maxLength={4000} onChange={(event) => setDraft(event.target.value)} placeholder="What am I missing?" />
        <div><span>{draft.length}/4000</span><div className="composer-actions">
          {voiceState === "listening" ? <button type="button" className="button button-secondary listening" onClick={() => { voiceSession.current?.stop(); setVoiceState("idle"); }}>Stop listening</button>
            : <button type="button" className="button button-secondary" onClick={listen}>{voiceState === "ready" ? "Voice ready" : "Use microphone"}</button>}
          <button type="button" className="button button-secondary" onClick={clear}>Clear conversation</button>
          <button className="button button-primary" disabled={!draft.trim() || sending}>{sending ? "Thinking…" : "Send"}</button>
        </div></div>
      </form>
    </section>
  </div>;
}
