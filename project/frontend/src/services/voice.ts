export type VoiceError = "permission_denied" | "no_speech" | "unavailable";

export interface VoiceCallbacks {
  onResult: (transcript: string) => void;
  onError: (error: VoiceError) => void;
  onEnd: () => void;
}

export interface VoiceSession {
  start: () => void;
  stop: () => void;
}

interface RecognitionEventLike { results: ArrayLike<{ 0: { transcript: string } }> }
interface RecognitionErrorLike { error: string }
interface RecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: RecognitionEventLike) => void) | null;
  onerror: ((event: RecognitionErrorLike) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}
type RecognitionConstructor = new () => RecognitionLike;

function recognitionConstructor(): RecognitionConstructor | null {
  const browserWindow = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition ?? null;
}

export function isVoiceInputSupported(): boolean {
  return recognitionConstructor() !== null;
}

export function createVoiceSession(callbacks: VoiceCallbacks): VoiceSession | null {
  const Constructor = recognitionConstructor();
  if (!Constructor) return null;
  const recognition = new Constructor();
  recognition.lang = navigator.language || "en-US";
  recognition.interimResults = false;
  recognition.continuous = false;
  recognition.onresult = (event) => callbacks.onResult(event.results[0]?.[0]?.transcript?.trim() ?? "");
  recognition.onerror = (event) => {
    if (event.error === "not-allowed" || event.error === "service-not-allowed") callbacks.onError("permission_denied");
    else if (event.error === "no-speech") callbacks.onError("no_speech");
    else callbacks.onError("unavailable");
  };
  recognition.onend = callbacks.onEnd;
  return { start: () => recognition.start(), stop: () => recognition.stop() };
}

export function isSpeechOutputSupported(): boolean {
  return "speechSynthesis" in window && typeof window.SpeechSynthesisUtterance === "function";
}

export function speakText(text: string, onEnd: () => void): boolean {
  if (!isSpeechOutputSupported()) return false;
  window.speechSynthesis.cancel();
  const utterance = new window.SpeechSynthesisUtterance(text);
  utterance.onend = onEnd;
  utterance.onerror = onEnd;
  window.speechSynthesis.speak(utterance);
  return true;
}

export function stopSpeaking(): void {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
