import { test } from "node:test";
import assert from "node:assert/strict";
import { average, band, compareScores, dimensionScores, overallScore, validScore } from "../shared/scoring";
import { sampleAnalysis } from "./helpers";

test("validScore accepts 0-10 and rejects -1 and junk", () => {
  assert.equal(validScore(7.26), 7.3);
  assert.equal(validScore(0), 0);
  assert.equal(validScore(-1), null);
  assert.equal(validScore(11), null);
  assert.equal(validScore("x"), null);
  assert.equal(validScore("8"), 8);
  assert.equal(validScore(null), null);
});

test("average ignores missing scores", () => {
  assert.equal(average({ plot: 8, acting: null, music: 6 }), 7);
  assert.equal(average({ plot: null }), null);
});

test("overallScore falls back to the dimension average", () => {
  const a = sampleAnalysis();
  a.critique.overall = null;
  assert.equal(overallScore(a.critique), 8);
  a.critique.overall = 9.1;
  assert.equal(overallScore(a.critique), 9.1);
});

test("band labels", () => {
  assert.equal(band(9.4), "Exceptional");
  assert.equal(band(5.2), "Mixed");
  assert.equal(band(null), "Not assessed");
});

test("compare: clear leader", () => {
  const a = dimensionScores(sampleAnalysis("A", {}).critique);
  const b = dimensionScores(sampleAnalysis("B", { plot: 5, acting: 5, music: 5, pacing: 5, themes: 5 }).critique);
  const result = compareScores(a, b);
  assert.equal(result.leader, "a");
  assert.equal(result.comparable, 8);
  assert.equal(result.rows.find((r) => r.key === "plot")?.outcome, "a");
});

test("compare: ties and close margins", () => {
  const a = dimensionScores(sampleAnalysis("A", { plot: 8.1 }).critique);
  const b = dimensionScores(sampleAnalysis("B", { plot: 8 }).critique);
  const result = compareScores(a, b);
  assert.equal(result.rows.find((r) => r.key === "plot")?.outcome, "tie");
  assert.equal(result.leader, "close");
});

test("compare: inconclusive when too few shared categories", () => {
  const a = dimensionScores(sampleAnalysis("A").critique);
  const b = dimensionScores(sampleAnalysis("B").critique);
  for (const key of ["plot", "acting", "music", "pacing", "themes"] as const) b[key] = null;
  const result = compareScores(a, b);
  assert.equal(result.leader, "inconclusive");
  assert.equal(result.comparable, 3);
});
