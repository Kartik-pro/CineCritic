import { test } from "node:test";
import assert from "node:assert/strict";
import { friendlyAuthError, MAX_PASSWORD, MIN_PASSWORD, validateEmail, validatePassword } from "../src/authValidation";

test("validateEmail accepts normal addresses and trims spaces", () => {
  assert.equal(validateEmail("  user@example.com "), "");
  assert.equal(validateEmail("first.last+tag@sub.example.co"), "");
});

test("validateEmail rejects empty and malformed addresses", () => {
  for (const bad of ["", "   ", "plain", "a@b", "a b@c.com", "@c.com", `${"a".repeat(250)}@x.com`]) {
    assert.notEqual(validateEmail(bad), "", `should reject ${JSON.stringify(bad)}`);
  }
});

test("validatePassword enforces length bounds", () => {
  assert.notEqual(validatePassword("x".repeat(MIN_PASSWORD - 1)), "");
  assert.equal(validatePassword("x".repeat(MIN_PASSWORD)), "");
  assert.equal(validatePassword("x".repeat(MAX_PASSWORD)), "");
  assert.notEqual(validatePassword("x".repeat(MAX_PASSWORD + 1)), "");
});

test("friendlyAuthError maps known Supabase messages", () => {
  assert.equal(friendlyAuthError("Invalid login credentials"), "Incorrect email or password.");
  assert.match(friendlyAuthError("Email not confirmed"), /confirm your email/i);
  assert.match(friendlyAuthError("Email rate limit exceeded"), /too many/i);
  assert.match(friendlyAuthError("New password should be different from the old password."), /different/i);
});

test("friendlyAuthError never echoes unknown or sensitive text", () => {
  const secret = "eyJhbGciOiJIUzI1NiJ9.secret-token";
  const message = friendlyAuthError(`boom ${secret}`);
  assert.ok(!message.includes(secret));
  assert.equal(friendlyAuthError(undefined), "Something went wrong. Please try again.");
});
