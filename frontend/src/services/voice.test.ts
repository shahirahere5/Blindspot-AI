import { afterEach, describe, expect, it, vi } from "vitest";
import { createVoiceSession, isSpeechOutputSupported, isVoiceInputSupported, speakText, stopSpeaking } from "./voice";

afterEach(() => {
  Reflect.deleteProperty(window, "SpeechRecognition");
  Reflect.deleteProperty(window, "webkitSpeechRecognition");
  Reflect.deleteProperty(window, "speechSynthesis");
  Reflect.deleteProperty(window, "SpeechSynthesisUtterance");
  vi.restoreAllMocks();
});

describe("browser voice abstraction", () => {
  it("reports unsupported recognition", () => {
    expect(isVoiceInputSupported()).toBe(false);
    expect(createVoiceSession({ onResult: vi.fn(), onError: vi.fn(), onEnd: vi.fn() })).toBeNull();
  });

  it("maps recognition transcript, permission errors, and stop", () => {
    let instance: FakeRecognition | undefined;
    class FakeRecognition {
      lang = ""; interimResults = true; continuous = true;
      onresult: ((event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      start = vi.fn(); stop = vi.fn();
      constructor() { instance = this; }
    }
    Object.defineProperty(window, "SpeechRecognition", { configurable: true, value: FakeRecognition });
    const onResult = vi.fn(); const onError = vi.fn(); const onEnd = vi.fn();
    const session = createVoiceSession({ onResult, onError, onEnd })!;
    session.start();
    instance!.onresult?.({ results: [{ 0: { transcript: "  grounded question  " } }] });
    instance!.onerror?.({ error: "not-allowed" });
    instance!.onend?.();
    session.stop();
    expect(onResult).toHaveBeenCalledWith("grounded question");
    expect(onError).toHaveBeenCalledWith("permission_denied");
    expect(onEnd).toHaveBeenCalled();
    expect(instance!.stop).toHaveBeenCalled();
  });

  it("starts and stops browser speech synthesis", () => {
    const cancel = vi.fn(); const speak = vi.fn();
    class Utterance { onend: (() => void) | null = null; onerror: (() => void) | null = null; constructor(public text: string) {} }
    Object.defineProperty(window, "speechSynthesis", { configurable: true, value: { cancel, speak } });
    Object.defineProperty(window, "SpeechSynthesisUtterance", { configurable: true, value: Utterance });
    expect(isSpeechOutputSupported()).toBe(true);
    expect(speakText("Answer", vi.fn())).toBe(true);
    expect(speak.mock.calls[0]![0].text).toBe("Answer");
    stopSpeaking();
    expect(cancel).toHaveBeenCalledTimes(2);
  });
});
