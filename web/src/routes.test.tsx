import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes, PATHS } from "./routes";

// The views open sockets and read `window`; these tests are about which page a URL reaches, so each view is a stub
// that says which one it is.
vi.mock("./views/Operator", () => ({ default: ({ demo }: { demo?: boolean }) => <p>{demo ? "operator demo" : "operator"}</p> }));
vi.mock("./views/Viewer", () => ({ default: () => <p>viewer</p> }));
vi.mock("./views/Multiview", () => ({ default: () => <p>multiview</p> }));

// MemoryRouter, the router both majors share, runs a layout effect that React warns about outside a browser.
// That warning alone is dropped; any other error still prints.
const consoleError = console.error;
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation((msg, ...rest) => {
    if (!String(msg).includes("useLayoutEffect does nothing on the server")) consoleError(msg, ...rest);
  });
});
afterEach(() => vi.restoreAllMocks());

const at = (url: string) =>
  renderToString(
    <MemoryRouter initialEntries={[url]}>
      <AppRoutes />
    </MemoryRouter>,
  );

describe("routes", () => {
  it.each([
    ["/operator", "<p>operator</p>"],
    ["/operator-demo", "<p>operator demo</p>"],
    ["/viewer", "<p>viewer</p>"],
    ["/multiview", "<p>multiview</p>"],
  ])("%s renders its page", (url, page) => {
    expect(at(url)).toBe(page);
  });

  it("serves the home page's links to every other page", () => {
    const home = at("/");
    expect(home).toContain("Control Room IQ");
    const hrefs = [...home.matchAll(/href="([^"]+)"/g)].map((m) => m[1]);
    expect(hrefs).toEqual(PATHS.filter((p) => p !== "/"));
  });

  it("keeps the viewer's settings in the query string out of the routing", () => {
    expect(at("/viewer?persona=coach&access=deaf&lang=es&allegiance=home")).toBe("<p>viewer</p>");
  });

  it("matches a trailing slash and any letter case, as a typed or bookmarked URL may have them", () => {
    expect(at("/operator/")).toBe("<p>operator</p>");
    expect(at("/Viewer")).toBe("<p>viewer</p>");
  });

  it("renders nothing for an unknown path", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {}); // the router's "No routes matched" note
    expect(at("/no-such-page")).toBe("");
  });
});
