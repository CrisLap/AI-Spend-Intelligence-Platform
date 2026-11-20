import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { assistant, auth, costSaving, setToken, setUnauthorizedHandler, type SSEEvent } from "./api";

const enc = new TextEncoder();

// A fetch() Response whose body arrives in the given chunks, exactly as the
// network would split it (not aligned to event boundaries).
function streamResponse(chunks: (string | Uint8Array)[], init: ResponseInit = { status: 200 }): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === "string" ? enc.encode(c) : c);
      controller.close();
    },
  });
  return new Response(stream, init);
}

async function collect(gen: AsyncGenerator<SSEEvent>): Promise<SSEEvent[]> {
  const out: SSEEvent[] = [];
  for await (const e of gen) out.push(e);
  return out;
}

describe("streamSSE (via costSaving.analyzeStream / assistant.sendStream)", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setToken("test-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
    setUnauthorizedHandler(null);
  });

  it("parses events and sends the auth + language headers (fetch, not EventSource)", async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        'event: step\ndata: {"index":0}\n\n',
        'event: done\ndata: {"answer":"ok"}\n\n',
      ]),
    );

    const events = await collect(costSaving.analyzeStream("cut costs", "forecast"));

    expect(events).toEqual([
      { event: "step", data: { index: 0 } },
      { event: "done", data: { answer: "ok" } },
    ]);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/cost-saving/analyze/stream?goal=cut%20costs&agent_type=forecast");
    expect(opts.headers.Authorization).toBe("Bearer test-token");
    expect(opts.headers["X-UI-Language"]).toBeTruthy();
  });

  it("reassembles an event split across arbitrary chunk boundaries", async () => {
    fetchMock.mockResolvedValue(
      streamResponse(['event: st', 'ep\ndata: {"a"', ":1}\n", "\nevent: done\ndata: {}\n\n"]),
    );

    const events = await collect(assistant.sendStream("hi"));

    expect(events).toEqual([
      { event: "step", data: { a: 1 } },
      { event: "done", data: {} },
    ]);
  });

  it("decodes a multi-byte character split between two chunks", async () => {
    const bytes = enc.encode('event: step\ndata: {"t":"€"}\n\n');
    const split = bytes.indexOf(0xe2) + 1; // inside the 3-byte "€"
    fetchMock.mockResolvedValue(streamResponse([bytes.slice(0, split), bytes.slice(split)]));

    const events = await collect(assistant.sendStream("x"));

    expect(events).toEqual([{ event: "step", data: { t: "€" } }]);
  });

  it("defaults the event name to 'message' and ignores blocks without data", async () => {
    fetchMock.mockResolvedValue(streamResponse([': keep-alive\n\n', 'data: {"n":1}\n\n']));

    expect(await collect(assistant.sendStream("x"))).toEqual([{ event: "message", data: { n: 1 } }]);
  });

  it("includes session_id in the assistant stream URL only when given", async () => {
    fetchMock.mockImplementation(async () => streamResponse([]));

    await collect(assistant.sendStream("a b", 7));
    await collect(assistant.sendStream("a b"));

    expect(fetchMock.mock.calls[0][0]).toBe("/api/assistant/stream?message=a%20b&session_id=7");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/assistant/stream?message=a%20b");
  });

  it("calls the unauthorized handler on 401 and throws a streamFailed error", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(new Response("nope", { status: 401 }));

    await expect(collect(costSaving.analyzeStream("g"))).rejects.toMatchObject({
      code: "streamFailed",
      status: 401,
    });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("throws streamingNotSupported when the response has no body", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, body: null });

    await expect(collect(costSaving.analyzeStream("g"))).rejects.toMatchObject({
      code: "streamingNotSupported",
    });
  });
});

describe("request() error handling", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("joins a FastAPI 422 detail array into a readable message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: [{ loc: ["body", "message"], msg: "too long", type: "x" }, { msg: "second" }] }),
          { status: 422 },
        ),
      ),
    );

    await expect(auth.login("a@b.c", "pw")).rejects.toThrow("too long; second");
  });

  it("surfaces a string detail as-is", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Invalid credentials" }), { status: 401 })),
    );

    await expect(auth.login("a@b.c", "pw")).rejects.toThrow("Invalid credentials");
  });
});
