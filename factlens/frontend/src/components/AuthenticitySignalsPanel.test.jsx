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

  it("downscopes media results into risk signals and exposes method caveats", () => {
    render(
      <AuthenticitySignalsPanel
        aiDetection={null}
        mediaDetection={{
          label: "NO_STRONG_SIGNAL",
          ai_probability: 0.21,
          explanation: "No strong synthetic-media cues were returned.",
          signals_found: ["no obvious artifact clusters"],
          analysis_mode: "vision_llm_heuristic",
          provider_label: "NVIDIA",
          model: "meta/llama-3.2-90b-vision-instruct",
          review_recommended: true,
          warnings: ["This is a heuristic synthetic-media review, not a forensic deepfake determination."],
          limitations: ["This result comes from a general vision LLM, not a forensic deepfake classifier."],
          media_url: "https://images.example/photo.png",
        }}
      />,
    );

    expect(screen.getByText("No strong synthetic-media signal")).toBeInTheDocument();
    expect(screen.getByText(/Vision-LLM heuristic via NVIDIA/i)).toBeInTheDocument();
    expect(screen.getByText(/not a forensic deepfake determination/i)).toBeInTheDocument();
    expect(screen.getByText(/not a forensic deepfake classifier/i)).toBeInTheDocument();
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
