import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Resync, RESYNC_GRACE_MS } from "./resync";
import { connectLive, type SocketLike } from "./useLiveSocket";

class FakeSocket implements SocketLike {
  static all: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: any }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSocket.all.push(this);
  }
  close() {
    this.closed = true;
  }
  send(msg: object) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  drop() {
    this.onclose?.();
  }
}

const latest = () => FakeSocket.all[FakeSocket.all.length - 1];

beforeEach(() => {
  vi.useFakeTimers();
  FakeSocket.all = [];
});
afterEach(() => vi.useRealTimers());

describe("connectLive (the socket under useLiveSocket)", () => {
  it("runs onOpen on the first connect and on each reconnect, before that connection's messages", () => {
    const log: string[] = [];
    const stop = connectLive("ws://x", {
      onMessage: (m) => log.push(`msg:${m.type}`),
      onOpen: () => log.push("open"),
      onState: (s) => log.push(`state:${s}`),
    }, (u) => new FakeSocket(u));

    latest().onopen?.();
    latest().send({ type: "match" });
    latest().drop();
    vi.advanceTimersByTime(1000); // first retry
    expect(FakeSocket.all).toHaveLength(2);
    latest().onopen?.();
    latest().send({ type: "proposal" });

    expect(log).toEqual([
      "state:live", "open", "msg:match", "state:down", "state:live", "open", "msg:proposal",
    ]);
    stop();
  });

  it("keeps the connection when onOpen throws", () => {
    const got: unknown[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const stop = connectLive("ws://x", {
      onMessage: (m) => got.push(m),
      onOpen: () => { throw new Error("boom"); },
      onState: () => undefined,
    }, (u) => new FakeSocket(u));
    latest().onopen?.();
    latest().send({ type: "match" });
    spy.mockRestore();
    expect(got).toEqual([{ type: "match" }]);
    expect(FakeSocket.all).toHaveLength(1);
    stop();
  });

  it("stops retrying once closed", () => {
    const stop = connectLive("ws://x", { onMessage: () => undefined, onState: () => undefined }, (u) => new FakeSocket(u));
    stop();
    expect(latest().closed).toBe(true);
    vi.advanceTimersByTime(20_000);
    expect(FakeSocket.all).toHaveLength(1);
  });
});

/** The console's wiring: the socket's onOpen and match frames drive a Resync, as Operator.tsx does. */
function consoleOnSocket() {
  const desk = { proposals: 0, desk: 0 };
  let shown: string | null = null;
  const resync = new Resync({ proposals: () => desk.proposals++, desk: () => desk.desk++ });
  const stop = connectLive("ws://x/ws/operator", {
    onMessage: (m) => {
      if (m.type === "match") {
        resync.match(m.meta?.match_id, shown);
        shown = m.meta?.match_id ?? null;
      }
    },
    onOpen: () => resync.opened(),
    onState: () => undefined,
  }, (u) => new FakeSocket(u));
  const reconnect = () => {
    latest().drop();
    vi.advanceTimersByTime(1000);
    latest().onopen?.();
  };
  return { desk, stop, reconnect };
}

describe("reconnect path (#52 review)", () => {
  it("a blip re-sending the same match drops only the proposals", () => {
    const c = consoleOnSocket();
    latest().onopen?.();
    latest().send({ type: "match", meta: { match_id: "m1" } });
    const before = { ...c.desk };

    c.reconnect();
    latest().send({ type: "match", meta: { match_id: "m1" } });
    vi.advanceTimersByTime(RESYNC_GRACE_MS * 2);

    expect(c.desk.proposals).toBe(before.proposals + 1);
    expect(c.desk.desk).toBe(before.desk); // moments, warnings, clock and the ended state survive
    c.stop();
  });

  it("a restarted API with another match clears the desk", () => {
    const c = consoleOnSocket();
    latest().onopen?.();
    latest().send({ type: "match", meta: { match_id: "m1" } });
    const before = c.desk.desk;

    c.reconnect();
    latest().send({ type: "match", meta: { match_id: "m2" } });
    expect(c.desk.desk).toBe(before + 1);
    c.stop();
  });

  it("a restarted API with no match clears the desk once the grace runs out", () => {
    const c = consoleOnSocket();
    latest().onopen?.();
    latest().send({ type: "match", meta: { match_id: "m1" } });
    const before = c.desk.desk;

    c.reconnect();
    vi.advanceTimersByTime(RESYNC_GRACE_MS - 1);
    expect(c.desk.desk).toBe(before);
    vi.advanceTimersByTime(1);
    expect(c.desk.desk).toBe(before + 1);
    c.stop();
  });

  it("Run again of the same match, outside a connect, still clears the desk", () => {
    const c = consoleOnSocket();
    latest().onopen?.();
    latest().send({ type: "match", meta: { match_id: "m1" } });
    const before = c.desk.desk;

    latest().send({ type: "match", meta: { match_id: "m1" } });
    expect(c.desk.desk).toBe(before + 1);
    c.stop();
  });
});
