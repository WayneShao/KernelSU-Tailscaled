import { expect, it } from "vitest";
import { controlURL, parseLoginResult } from "./server";

it.each([
  "https://example.com'; id #", "https://example.com/$(id)",
  "https://user:password@example.com", "https://example.com?token=x",
  "https://example.com#fragment", "https://example.com\nextra",
  "https://example.com:65536", "file:///tmp/test", "javascript:alert(1)",
])("rejects unsafe server input: %s", value => {
  expect(() => controlURL(value)).toThrow();
});

it("accepts private servers, IPv6 and custom ports without shell interpretation", () => {
  expect(controlURL("http://192.168.1.2:8080/")).toBe("http://192.168.1.2:8080");
  expect(controlURL("https://[fd00::1]:8443")).toBe("https://[fd00::1]:8443");
});

it.each(["javascript:alert(1)", "https://user:password@example.com/login"])("refuses unsafe authentication links: %s", authURL => {
  expect(() => parseLoginResult(JSON.stringify({ controlURL: "https://headscale.example.com", authURL }))).toThrow();
});
