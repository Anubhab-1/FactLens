import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AuthenticitySignalsPanel from "./AuthenticitySignalsPanel";

describe("AuthenticitySignalsPanel", () => {
  it("shows readable method metadata for text authenticity review", () => {
    render(
      <AuthenticitySignalsPanel
        aiDetection={{
          label: "LIKELY_HUMAN",
          ai_probability: 0.18,
          explanation: "The writing keeps uneven cadence and specific phrasing.",
          signals_found: ["specific phrasing"],
          analysis_mode: "text_llm_stylistic_review",
          provider_label: "Google Gemini",
          model: "gemini-1.5-pro",
          review_recommended: false,
          warnings: [],
          limitations: ["This is a stylistic estimate, not proof of authorship."],
        }}
        mediaDetection={null}
      />,
    );

    expect(screen.getByText("Likely human-written text")).toBeInTheDocument();
    expect(screen.getByText(/Stylistic LLM review via Google Gemini/i)).toBeInTheDocument();
    expect(screen.getByText(/This is a stylistic estimate, not proof of authorship/i)).toBeInTheDocument();
  });

  it("shows explicit unavailability when no specialized media classifier is available", () => {
    render(
      <AuthenticitySignalsPanel
        aiDetection={null}
        mediaDetection={{
          label: "UNKNOWN",
          ai_probability: null,
          explanation: "Visual media authenticity review is unavailable because no specialized classifier endpoint is configured.",
          signals_found: [],
          analysis_mode: "unavailable",
          review_recommended: true,
          warnings: ["Visual media review is unavailable because FactLens no longer uses the vision-LLM fallback."],
          limitations: [],
          media_url: "https://images.example/photo.png",
        }}
      />,
    );

    expect(screen.getByText("Visual media review unavailable")).toBeInTheDocument();
    expect(screen.getByText(/^Unavailable$/i)).toBeInTheDocument();
    expect(screen.getByText(/no longer uses the vision-LLM fallback/i)).toBeInTheDocument();
  });

  it("stacks cards in compact mode for narrow sidebar layouts", () => {
    render(
      <AuthenticitySignalsPanel
        compact
        aiDetection={{
          label: "LIKELY_HUMAN",
          ai_probability: 0.18,
          explanation: "The writing keeps uneven cadence and specific phrasing.",
          signals_found: ["specific phrasing"],
        }}
        mediaDetection={{
          label: "NO_STRONG_SIGNAL",
          ai_probability: 0.21,
          explanation: "No strong synthetic-media cues were returned.",
          signals_found: ["no obvious artifact clusters"],
          media_url: "https://images.example/photo.png",
        }}
      />,
    );

    expect(screen.getByTestId("authenticity-signals-layout")).toHaveClass("space-y-4");
    expect(screen.getByTestId("authenticity-signals-layout")).not.toHaveClass("lg:grid-cols-2");
  });
});
