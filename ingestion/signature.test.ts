// Run: npx tsx --test ingestion/signature.test.ts   (FF 180 security test SEC-05)
import { test } from "node:test";
import assert from "node:assert/strict";
import crypto from "crypto";
import { verifySignature } from "./signature";

const secret = "test-secret";
const body = Buffer.from(JSON.stringify({ zen: "Keep it logically awesome." }));
const valid = "sha256=" + crypto.createHmac("sha256", secret).update(body).digest("hex");

test("accepts a correctly signed payload", () => {
  assert.equal(verifySignature(body, valid, secret), true);
});

test("rejects a payload signed with the wrong secret", () => {
  const forged = "sha256=" + crypto.createHmac("sha256", "attacker").update(body).digest("hex");
  assert.equal(verifySignature(body, forged, secret), false);
});

test("rejects a tampered body", () => {
  assert.equal(verifySignature(Buffer.from('{"zen":"tampered"}'), valid, secret), false);
});

test("rejects a short forged header without throwing", () => {
  assert.equal(verifySignature(body, "sha256=abc", secret), false);
});

test("rejects when the header or server secret is missing", () => {
  assert.equal(verifySignature(body, undefined, secret), false);
  assert.equal(verifySignature(body, valid, undefined), false);
});
