import test from "node:test";
import assert from "node:assert/strict";
import {
  describeFindMyError,
  isFindMyLocationMessage,
  normalizeLocationSnapshot,
  resolveFindMyLocation,
} from "../findmy-location.mjs";

const findMyMessage = {
  balloonBundleId:
    "com.apple.messages.MSMessageExtensionBalloonPlugin:0000000000:com.apple.findmy.FindMyMessagesApp",
  content: { type: "custom", raw: { imessage_type: "unsupported-message" } },
  sender: { id: "+15551234567" },
  space: { phone: "shared" },
};

test("recognizes Find My location cards only", () => {
  assert.equal(isFindMyLocationMessage(findMyMessage), true);
  assert.equal(isFindMyLocationMessage({ ...findMyMessage, balloonBundleId: "other" }), false);
});

test("normalizes a valid shared-location snapshot", () => {
  assert.deepEqual(
    normalizeLocationSnapshot({ latitude: 29.7, longitude: -95.4, accuracy: 8, shortAddress: "Houston" }),
    { type: "location", latitude: 29.7, longitude: -95.4, accuracy: 8, name: "", address: "", shortAddress: "Houston", longAddress: "", locationType: "" },
  );
});

test("resolves Find My through a one-shot shared client", async () => {
  let closed = false;
  let requested = "";
  const result = await resolveFindMyLocation({
    message: findMyMessage,
    projectId: "project",
    projectSecret: "secret",
    issueTokens: async () => ({ type: "shared", token: "token" }),
    createClient: () => ({
      locations: {
        get: async (address) => {
          requested = address;
          return { latitude: 29.7, longitude: -95.4, locationType: "legacy" };
        },
      },
      close: async () => { closed = true; },
    }),
  });
  assert.equal(requested, "+15551234567");
  assert.equal(result.type, "location");
  assert.equal(result.locationType, "legacy");
  assert.equal(closed, true);
});


test("a failing close does not mask the resolution error", async () => {
  await assert.rejects(
    resolveFindMyLocation({
      message: findMyMessage,
      projectId: "project",
      projectSecret: "secret",
      issueTokens: async () => ({ type: "shared", token: "token" }),
      createClient: () => ({
        locations: { get: async () => { throw new Error("get-failed"); } },
        close: async () => { throw new Error("close-failed"); },
      }),
    }),
    /get-failed/
  );
});

test("describeFindMyError never leaks the raw error message", () => {
  const described = describeFindMyError({
    message: "Bearer abc123 at secret.endpoint:443",
    code: 14,
    name: "GrpcError",
  });
  assert.equal(described, "14");
  assert.equal(described.includes("abc123"), false);
  assert.equal(describeFindMyError(new Error("boom")), "Error");
  assert.equal(describeFindMyError(null), "unknown error");
});

test("resolution degrades to null when the client factory is unavailable", async () => {
  const result = await resolveFindMyLocation({
    message: findMyMessage,
    projectId: "project",
    projectSecret: "secret",
    issueTokens: async () => ({ type: "shared", token: "token" }),
    createClient: undefined,
  });
  assert.equal(result, null);
});
