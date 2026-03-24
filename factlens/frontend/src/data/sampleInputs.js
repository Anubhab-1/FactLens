export const sampleInputs = [
  {
    id: "clean-truth-pack",
    label: "Clean truth pack",
    mode: "text",
    description: "Stable scientific and geographic facts for a fast, high-confidence walkthrough.",
    challenge: "Strong support, low conflict",
    talkingPoint: "Use this first to show the pipeline behaving cleanly from extraction through verification.",
    value:
      "The Pacific Ocean is the largest ocean on Earth. Mount Everest is the highest mountain above sea level. The Eiffel Tower is in Paris.",
  },
  {
    id: "mixed-verdict-pack",
    label: "Mixed verdict pack",
    mode: "text",
    description: "A short pack with true and false claims so the report shows multiple verdict types in one run.",
    challenge: "Mixed verdicts",
    talkingPoint: "Use this to show how FactLens separates clearly supported claims from clearly false ones.",
    value:
      "Paris is the capital of France. The Eiffel Tower is in Paris. Berlin is the capital of Italy. Water boils at 100 degrees Celsius at sea level.",
  },
  {
    id: "time-sensitive-pack",
    label: "Time-sensitive pack",
    mode: "text",
    description: "Current-role claims that force the system to care about dated and recent evidence.",
    challenge: "Freshness stress test",
    talkingPoint: "Use this to show recency warnings, dated-source coverage, and search recovery behavior.",
    value:
      "The current CEO of Microsoft is Satya Nadella. The current Prime Minister of India is Narendra Modi.",
  },
  {
    id: "live-url-pack",
    label: "Live article URL",
    mode: "url",
    description: "Paste a real news URL to demonstrate article scraping, claim review, and evidence conflict on live data.",
    challenge: "Live news + ambiguity",
    talkingPoint: "Use this last in the presentation to show the product handling realistic, messy source material.",
    value: "",
  },
  {
    id: "contested-fact-pack",
    label: "Contested fact pack",
    mode: "text",
    description: "Common myths that trigger the 'Side-by-Side Conflict' UI by hitting legacy vs modern consensus.",
    challenge: "Dueling sources / Conflict",
    talkingPoint: "Use this to dramatically show the 'Dueling Sources' UI when FactLens hits legitimate search-time disagreement.",
    value:
      "The Great Wall of China is the only man-made structure visible from space with the naked eye.",
  },
];
