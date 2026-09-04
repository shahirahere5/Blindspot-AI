import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatView } from "./ChatView";
import { ApiError } from "../services/api";
import { documentFixture } from "../test/fixtures";
import type { Conversation, ConversationMessage } from "../types/api";

const apiMocks = vi.hoisted(() => ({
  createConversation: vi.fn(), getConversation: vi.fn(),
  sendConversationMessage: vi.fn(), clearConversation: vi.fn(),
}));
const voiceMocks = vi.hoisted(() => ({
  isVoiceInputSupported: vi.fn(), createVoiceSession: vi.fn(),
  isSpeechOutputSupported: vi.fn(), speakText: vi.fn(), stopSpeaking: vi.fn(),
}));

vi.mock("../services/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("../services/api")>(), ...apiMocks,
}));
vi.mock("../services/voice", () => voiceMocks);

const emptyConversation: Conversation = {
  conversation_id: "conv_11111111111111111111111111111111",
  document_id: documentFixture.document_id,
  scope: "document", version_group_id: null,
  created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:00:00Z", messages: [],
};
const userMessage: ConversationMessage = {
  message_id: "msg_user", role: "user", content: "What is the biggest risk?",
  created_at: "2026-09-04T00:00:01Z", sources: [], related_findings: [], metadata: {},
};
const assistantMessage: ConversationMessage = {
  message_id: "msg_assistant", role: "assistant", content: "Customer concentration is the largest risk.",
  created_at: "2026-09-04T00:00:02Z",
  sources: [{ source_id: "src_1", document_id: documentFixture.document_id, source_type: "page", source_location: 2, version_number: null, visual_derived: false, excerpt: "Revenue depends on one customer." }],
  related_findings: [{ node_id: "gn_1", type: "risk", label: "Customer concentration" }], metadata: {},
};

beforeEach(() => {
  sessionStorage.clear();
  Object.values(apiMocks).forEach((mock) => mock.mockReset());
  Object.values(voiceMocks).forEach((mock) => mock.mockReset());
  voiceMocks.isVoiceInputSupported.mockReturnValue(false);
  voiceMocks.isSpeechOutputSupported.mockReturnValue(false);
  voiceMocks.stopSpeaking.mockImplementation(() => undefined);
});

describe("grounded chat", () => {
  it("shows an empty state, suggested prompt, optimistic loading, answer sources, and clear", async () => {
    const user = userEvent.setup();
    apiMocks.createConversation.mockResolvedValue(emptyConversation);
    let finish: ((value: unknown) => void) | undefined;
    apiMocks.sendConversationMessage.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    apiMocks.clearConversation.mockResolvedValue(emptyConversation);
    render(<ChatView document={documentFixture} />);

    expect(screen.getByText("What would you like to examine?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "What are the highest risks?" }));
    expect(screen.getByLabelText(/Ask about this document/)).toHaveValue("What are the highest risks?");
    await user.clear(screen.getByLabelText(/Ask about this document/));
    await user.type(screen.getByLabelText(/Ask about this document/), userMessage.content);
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByRole("status")).toHaveTextContent("Finding grounded evidence");
    expect(screen.getByText(userMessage.content)).toBeInTheDocument();
    finish?.({ conversation_id: emptyConversation.conversation_id, message: assistantMessage, conversation: { ...emptyConversation, messages: [userMessage, assistantMessage] } });

    expect(await screen.findByText(assistantMessage.content)).toBeInTheDocument();
    expect(screen.getByText("Page 2")).toBeInTheDocument();
    expect(screen.getByText(/risk · Customer concentration/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear conversation" }));
    await waitFor(() => expect(apiMocks.clearConversation).toHaveBeenCalledOnce());
    expect(await screen.findByText("What would you like to examine?")).toBeInTheDocument();
  });

  it("restores history and changes to explicit version-series scope", async () => {
    sessionStorage.setItem(`blindspot-conversation:${documentFixture.document_id}:document`, emptyConversation.conversation_id);
    apiMocks.getConversation.mockResolvedValue({ ...emptyConversation, messages: [userMessage, assistantMessage] });
    render(<ChatView document={documentFixture} />);
    expect(await screen.findByText(assistantMessage.content)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Version series" }));
    expect(screen.getByText(`Version series · ${documentFixture.filename}`)).toBeInTheDocument();
    expect(screen.getByLabelText(/Ask about this version series/)).toBeInTheDocument();
  });

  it("keeps text available when voice is unsupported or permission is denied", async () => {
    const user = userEvent.setup();
    const callbacks: { onError?: (reason: string) => void } = {};
    render(<ChatView document={documentFixture} />);
    await user.click(screen.getByRole("button", { name: "Use microphone" }));
    expect(screen.getByRole("alert")).toHaveTextContent("isn't available in this browser");
    expect(screen.getByLabelText(/Ask about this document/)).toBeEnabled();

    voiceMocks.isVoiceInputSupported.mockReturnValue(true);
    voiceMocks.createVoiceSession.mockImplementation((value) => { Object.assign(callbacks, value); return { start: vi.fn(), stop: vi.fn() }; });
    await user.click(screen.getByRole("button", { name: "Use microphone" }));
    act(() => callbacks.onError?.("permission_denied"));
    expect(await screen.findByRole("alert")).toHaveTextContent("permission was denied");
  });

  it("places recognized speech in the editable input and can cancel listening", async () => {
    const user = userEvent.setup();
    let callbacks: { onResult: (value: string) => void } | undefined;
    const stop = vi.fn();
    voiceMocks.isVoiceInputSupported.mockReturnValue(true);
    voiceMocks.createVoiceSession.mockImplementation((value) => { callbacks = value; return { start: vi.fn(), stop }; });
    render(<ChatView document={documentFixture} />);
    await user.click(screen.getByRole("button", { name: "Use microphone" }));
    expect(screen.getByRole("button", { name: "Stop listening" })).toBeInTheDocument();
    act(() => callbacks?.onResult("What am I missing?"));
    expect(screen.getByLabelText(/Ask about this document/)).toHaveValue("What am I missing?");
    await user.click(screen.getByRole("button", { name: "Voice ready" }));
    expect(screen.getByRole("button", { name: "Stop listening" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop listening" }));
    expect(stop).toHaveBeenCalled();
  });

  it("starts and stops speech synthesis and displays safe backend errors", async () => {
    sessionStorage.setItem(`blindspot-conversation:${documentFixture.document_id}:document`, emptyConversation.conversation_id);
    apiMocks.getConversation.mockResolvedValue({ ...emptyConversation, messages: [assistantMessage] });
    voiceMocks.isSpeechOutputSupported.mockReturnValue(true);
    voiceMocks.speakText.mockReturnValue(true);
    render(<ChatView document={documentFixture} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Speak" }));
    expect(voiceMocks.speakText).toHaveBeenCalledWith(assistantMessage.content, expect.any(Function));
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(voiceMocks.stopSpeaking).toHaveBeenCalled();

    apiMocks.sendConversationMessage.mockRejectedValue(new ApiError("The AI service rate limit was reached. Please wait and try again.", 429));
    await user.type(screen.getByLabelText(/Ask about this document/), "Follow up");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("rate limit was reached");
  });
});
