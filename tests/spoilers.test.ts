import { test } from "node:test";
import assert from "node:assert/strict";
import { effectiveLevel, enforce, spoilerInstructions, stripSpoilers } from "../server/spoilers";
import { sanitizeCritique, capWords } from "../server/critique";
import { critiqueJson } from "./helpers";

test("stripSpoilers drops outcome sentences only", () => {
  const result = stripSpoilers("A tense heist drama. The hero dies in the end. Great score.", false);
  assert.equal(result.text, "A tense heist drama. Great score.");
  assert.equal(result.removed, 1);
});

test("strict mode also drops suggestive cues", () => {
  assert.equal(stripSpoilers("It builds to a shocking climax.", false).removed, 0);
  assert.equal(stripSpoilers("It builds to a shocking climax.", true).removed, 1);
});

test("fully removed text becomes a placeholder", () => {
  assert.equal(stripSpoilers("He dies.", false).text, "Details withheld to avoid spoilers.");
});

test("effectiveLevel falls back to none", () => {
  assert.equal(effectiveLevel("full"), "full");
  assert.equal(effectiveLevel("everything"), "none");
  assert.equal(effectiveLevel(undefined), "none");
});

test("instructions vary by level", () => {
  assert.match(spoilerInstructions("none"), /empty string/);
  assert.match(spoilerInstructions("light"), /midpoint/);
  assert.match(spoilerInstructions("full"), /the ending/);
});

test("enforce cleans fields and clears notes when spoiler-free", () => {
  const raw = critiqueJson();
  raw.verdictText = "A great watch. It turns out the narrator lied.";
  raw.spoilerNotes = "The hero dies.";
  const critique = sanitizeCritique(raw);
  const removed = enforce(critique, "none");
  assert.equal(removed, 1);
  assert.equal(critique.verdictText, "A great watch.");
  assert.equal(critique.spoilerNotes, "");
});

test("enforce keeps full spoiler notes and trims light ones", () => {
  const raw = critiqueJson();
  raw.spoilerNotes = "The hero dies at the end.";
  assert.equal(enforce(sanitizeCritique(raw), "full"), 0);
  const light = sanitizeCritique(raw);
  enforce(light, "light");
  assert.equal(light.spoilerNotes, "Details withheld to avoid spoilers.");
});

test("sanitizeCritique tolerates malformed model output", () => {
  const critique = sanitizeCritique({ plot: { score: -1 }, overall: "n/a", quickTake: "oops", strengths: [1, "ok"] });
  assert.equal(critique.dimensions.plot.score, null);
  assert.equal(critique.dimensions.acting.summary, "");
  assert.equal(critique.overall, null);
  assert.deepEqual(critique.quickTake, []);
  assert.deepEqual(critique.strengths, ["ok"]);
});

test("capWords limits the quick take to the word budget", () => {
  const lines = ["- one two three four five six", "- seven eight nine ten", "eleven twelve thirteen"];
  const out = capWords(lines, 9);
  assert.equal(out[0], "one two three four five six");
  assert.equal(out[1], "seven eight nine…");
  assert.equal(out.length, 2);
  assert.deepEqual(capWords(lines, 8), ["one two three four five six"]);
});
