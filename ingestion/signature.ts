import crypto from "crypto";

/** Verifies GitHub's X-Hub-Signature-256 header (HMAC-SHA256 of the raw request body). */
export function verifySignature(rawBody: Buffer | undefined, signature: string | undefined, secret: string | undefined): boolean {
  if (!signature || !secret || !rawBody) return false;

  const digest = "sha256=" + crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  const expected = Buffer.from(digest);
  const received = Buffer.from(signature);
  // timingSafeEqual throws on unequal lengths, so a forged short header must be rejected first.
  return expected.length === received.length && crypto.timingSafeEqual(expected, received);
}
