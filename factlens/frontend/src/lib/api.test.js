import { describe, expect, it } from "vitest";

import { resolveApiUrl } from "./api";

describe("api", () => {
  it("uses an explicit VITE_API_URL when present", () => {
    expect(resolveApiUrl("https://api.example.com/")).toBe("https://api.example.com");
  });

  it("derives the default API origin from the current browser hostname", () => {
    expect(
      resolveApiUrl(undefined, {
        hostname: "127.0.0.1",
        protocol: "http:",
      }),
    ).toBe("http://127.0.0.1:8000");
  });

  it("falls back to localhost when no browser location is available", () => {
    expect(resolveApiUrl(undefined, null)).toBe("http://localhost:8000");
  });
});
