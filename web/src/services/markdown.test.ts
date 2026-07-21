import { describe, expect, it } from "vitest";
import { googleRefs, renderMd } from "./markdown";

describe("renderMd", () => {
  it("renders markdown to escaped HTML", () => {
    expect(renderMd("**bold**")).toContain("<strong>bold</strong>");
  });

  it("returns empty string for empty input", () => {
    expect(renderMd("")).toBe("");
  });
});

describe("googleRefs", () => {
  it("returns empty array for empty query", () => {
    expect(googleRefs("")).toEqual([]);
  });

  it("returns search links for a query", () => {
    const refs = googleRefs("python");
    expect(refs).toHaveLength(3);
    expect(refs[0].url).toContain(encodeURIComponent("python"));
  });

  it("truncates query to 120 chars", () => {
    const long = "a".repeat(200);
    const refs = googleRefs(long);
    expect(refs[0].label).toContain("a".repeat(120));
    expect(refs[0].label).not.toContain("a".repeat(121));
  });
});
