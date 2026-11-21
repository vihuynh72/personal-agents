import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";

const API_URL = (process.env.API_URL ?? "https://personal-agents-production-81468651.up.railway.app").replace(/\/+$/, "");
const INTERIM_MS = 3_000;
const TIMEOUT_MS = 600_000; // a new cook list can take a few minutes of store lookups
const SORRY = "Sorry, I hit a problem on my side. Try again in a minute.";

const OUTBOX_POLL_MS = Number(process.env.OUTBOX_POLL_MS) || 3_000;

type Send = (text: string) => Promise<unknown>;

// One inbound text -> backend -> reply. Never throws.
async function bridge(
  sender: string,
  text: string,
  send: Send,
  wrap: (fn: () => Promise<void>) => Promise<void> = (fn) => fn(),
  apiUrl = API_URL,
): Promise<void> {
  console.log("INBOUND", sender.slice(-4), text);
  await wrap(async () => {
    let done = false;
    const interim = setTimeout(() => {
      if (!done) send("On it, give me a minute.").catch((e) => console.error("interim send failed", e));
    }, INTERIM_MS);
    let reply = SORRY;
    try {
      const res = await fetch(`${apiUrl}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sender, text }),
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      if (!res.ok) throw new Error(`backend ${res.status}`);
      const body = (await res.json()) as { reply?: unknown };
      if (typeof body.reply !== "string" || !body.reply) throw new Error("backend returned no reply");
      reply = body.reply;
    } catch (e) {
      console.error("BRIDGE ERROR", sender.slice(-4), e);
    } finally {
      done = true;
      clearTimeout(interim);
    }
    await send(reply).catch((e) => console.error("send failed", e));
  }).catch((e) => console.error("bridge failed", e));
}

// Backend -> person push. resolve() maps a sender id to a Send, or undefined if we have no conversation for them.
// The returned tick never overlaps itself and never throws; a failed fetch or send is logged and skipped.
function makeOutbox(
  resolve: (sender: string) => Promise<Send | undefined>,
  apiUrl = API_URL,
  log: (line: string) => void = console.log,
) {
  let running = false;
  let lastWarn = 0;
  return async function tick(): Promise<void> {
    if (running) return;
    running = true;
    try {
      let messages: { sender: string; text: string }[] = [];
      try {
        const res = await fetch(`${apiUrl}/outbox`, { signal: AbortSignal.timeout(10_000) });
        if (!res.ok) throw new Error(`outbox ${res.status}`); // 404 until the backend ships it
        const body = (await res.json()) as { messages?: unknown };
        if (Array.isArray(body.messages)) messages = body.messages;
      } catch (e) {
        if (Date.now() - lastWarn > 60_000) {
          lastWarn = Date.now();
          log(`OUTBOX poll failed: ${e instanceof Error ? e.message : e}`);
        }
        return;
      }
      for (const m of messages) {
        try {
          if (typeof m?.sender !== "string" || typeof m?.text !== "string") continue;
          const send = await resolve(m.sender);
          if (!send) {
            log(`OUTBOX no conversation for ${m.sender.slice(-4)}`);
            continue; // server already removed it; no retry
          }
          await send(m.text);
          log(`OUTBOX sent to ${m.sender.slice(-4)}`);
        } catch (e) {
          console.error("OUTBOX send failed", m?.sender?.slice?.(-4), e);
        }
      }
    } finally {
      running = false;
    }
  };
}

async function selftest() {
  let outboxHits = 0;
  const server = Bun.serve({
    port: 0,
    async fetch(req) {
      if (new URL(req.url).pathname === "/outbox") {
        outboxHits++;
        await Bun.sleep(100); // long enough for a second concurrent tick to be skipped
        if (outboxHits === 1) return new Response("not deployed", { status: 404 });
        if (outboxHits === 2)
          return Response.json({
            messages: [
              { sender: "+15551110001", text: "boom" },
              { sender: "+15551110001", text: "receipt for fast-user" },
              { sender: "+15559990000", text: "receipt for a stranger" },
            ],
          });
        return Response.json({ messages: [] });
      }
      if (new URL(req.url).pathname !== "/messages") return new Response("nope", { status: 404 });
      const { sender, text } = (await req.json()) as { sender: string; text: string };
      if (text === "slow") await Bun.sleep(5_000);
      return Response.json({ reply: `canned reply to ${text} from ${sender}` });
    },
  });
  const url = `http://localhost:${server.port}`;
  const t0 = Date.now();
  const out: string[] = [];
  const mk = (tag: string): Send => async (t) => void out.push(`[${((Date.now() - t0) / 1000).toFixed(1)}s] to ${tag}: ${t}`);
  await Promise.all([
    bridge("+15551110001", "fast", mk("fast-user"), undefined, url),
    bridge("+15551110002", "slow", mk("slow-user"), undefined, url),
    bridge("+15551110003", "x", mk("dead-backend-user"), undefined, "http://localhost:1"),
  ]);
  // Outbox: "+15551110001" has texted above (known), "+15559990000" has not. Poll 1 = 404, poll 2 = messages, poll 3 = empty.
  const logs: string[] = [];
  const fast = mk("fast-user");
  const known: Send = async (t) => {
    if (t === "boom") throw new Error("send exploded");
    return fast(t);
  };
  const tick = makeOutbox(async (s) => (s === "+15551110001" ? known : undefined), url, (l) => logs.push(l));
  await tick(); // 404 tolerated
  await tick();
  await Promise.all([tick(), tick()]); // overlap: second is skipped
  server.stop(true);
  console.log(out.join("\n"));
  console.log(logs.join("\n"));
  const ok =
    outboxHits === 3 &&
    out.filter((l) => l.includes("fast-user: receipt for fast-user")).length === 1 &&
    !out.some((l) => l.includes("stranger")) &&
    logs.filter((l) => l === "OUTBOX no conversation for 0000").length === 1 &&
    logs.filter((l) => l.startsWith("OUTBOX poll failed")).length === 1 &&
    out.some((l) => l.includes("fast-user: canned reply")) &&
    out.filter((l) => l.includes("slow-user: On it")).length === 1 &&
    out.some((l) => l.includes("slow-user: canned reply")) &&
    !out.some((l) => l.includes("fast-user: On it")) &&
    out.some((l) => l.includes(`dead-backend-user: ${SORRY}`));
  console.log(ok ? "SELFTEST OK" : "SELFTEST FAILED");
  process.exit(ok ? 0 : 1);
}

if (process.argv.includes("--selftest")) {
  await selftest();
} else {
  const app = await Spectrum({
    projectId: process.env.PROJECT_ID!,
    projectSecret: process.env.PROJECT_SECRET!,
    providers: [imessage.config()],
  });

  // Conversation per sender, in memory. Ids are also persisted so a restart can reopen a DM via
  // imessage(app).user(id) + space.create(user) (docs: spaces-and-users.md "Creating a space").
  // File name ends in .log only so the existing *.log gitignore keeps phone numbers out of git.
  const SENDERS_FILE = new URL("../.outbox-senders.log", import.meta.url).pathname;
  const spaces = new Map<string, { send: Send }>();
  const persisted = new Set<string>(await Bun.file(SENDERS_FILE).json().catch(() => []));
  const im = imessage(app);
  const outbox = makeOutbox(async (sender) => {
    let space = spaces.get(sender);
    if (!space && persisted.has(sender)) {
      space = await im.space.create(await im.user(sender));
      spaces.set(sender, space);
    }
    return space && ((t) => space.send(t));
  });
  setInterval(() => void outbox(), OUTBOX_POLL_MS);

  for await (const [space, message] of app.messages) {
    if (message.direction === "outbound") continue;
    const send: Send = (t) => space.send(t);
    if (message.content.type !== "text") {
      send("Text only for now, sorry.").catch((e) => console.error("send failed", e));
      continue;
    }
    // Stable sender: message.sender.id (docs: messages.md "sender"), falling back to the space id.
    const sender = message.sender?.id ?? space.id;
    spaces.set(sender, space);
    if (message.sender?.id && !persisted.has(sender)) {
      persisted.add(sender);
      Bun.write(SENDERS_FILE, JSON.stringify([...persisted])).catch((e) => console.error("persist failed", e));
    }
    // Not awaited: one slow order must not block other conversations.
    void bridge(sender, message.content.text, send, (fn) => space.responding(fn));
  }
}
