import type { AnalysisReport, DebateResult, NormalizedDocument } from "../types/api";

export const documentFixture: NormalizedDocument = {
  document_id: "doc_test-123",
  filename: "strategy.pdf",
  file_type: "pdf",
  status: "processed",
  content: [
    { type: "page", location: 1, text: "Market context", extra: {} },
    { type: "page", location: 2, text: "Revenue depends on one customer.", extra: {} },
  ],
  metadata: { page_count: 2 },
  warnings: [],
};

export const analysisFixture: AnalysisReport = {
  document_id: documentFixture.document_id,
  status: "completed",
  summary: "The strategy has a promising market but concentrated revenue exposure.",
  overall_assessment: "Validate demand and diversify before scaling.",
  risks: [{
    title: "Customer concentration",
    description: "One customer accounts for most planned revenue.",
    severity: "high",
    evidence: "Revenue depends on one customer.",
    source_locations: [2],
    recommendation: "Build a diversified pipeline.",
  }],
  assumptions: [{
    title: "Demand remains stable",
    description: "The plan assumes stable demand.",
    confidence: "medium",
    evidence: "Market context",
    source_locations: [1],
    why_it_matters: "Demand drives the forecast.",
  }],
  biases: [],
  missing_perspectives: [{
    perspective: "Customer operations",
    description: "Operational buyers were not represented.",
    why_it_matters: "They own adoption.",
    questions_to_consider: ["Who will operate the product?"],
  }],
  unanswered_questions: [{ question: "What is the fallback plan?", importance: "high", reason: "Resilience is unclear." }],
  recommendations: [{ priority: "high", title: "Diversify demand", description: "Secure three independent pilots." }],
  metadata: { rag_enabled: true, model: "test-model" },
};

export const debateFixture: DebateResult = {
  document_id: documentFixture.document_id,
  status: "completed",
  agent_analyses: [{
    agent: "skeptic",
    role: "Challenges weak claims",
    status: "succeeded",
    error: null,
    summary: "The growth case is under-evidenced.",
    findings: [{
      title: "Unvalidated growth",
      description: "The forecast lacks independent validation.",
      severity: "high",
      evidence: "Revenue depends on one customer.",
      source_locations: [2],
      recommendation: "Test the forecast.",
    }],
    assumptions: [],
    questions: [],
    confidence: "high",
    metadata: {},
  }],
  agreements: ["Demand validation is essential."],
  disagreements: ["The panel differs on timing."],
  final_blind_spots: ["No downside scenario."],
  final_risks: analysisFixture.risks,
  final_assumptions: analysisFixture.assumptions,
  final_biases: [],
  missing_perspectives: analysisFixture.missing_perspectives,
  unanswered_questions: analysisFixture.unanswered_questions,
  recommendations: analysisFixture.recommendations,
  overall_assessment: "Proceed only after validating the core assumptions.",
  metadata: { successful_agents: ["skeptic"], rag_enabled: true },
};
