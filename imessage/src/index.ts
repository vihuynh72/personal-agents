import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";

const API_URL = (process.env.API_URL ?? "https://personal-agents-production-81468651.up.railway.app").replace(/\/+$/, "");
const INTERIM_MS = 3_000;
const TIMEOUT_MS = 150_000;
const SORRY = "Sorry, I hit a problem on my side. Try again in a minute.";

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

async function selftest() {
  const server = Bun.serve({
    port: 0,
    async fetch(req) {
      const { sender, text } = (await req.json()) as { sender: string; text: string };
      if (new URL(req.url).pathname !== "/messages") return new Response("nope", { status: 404 });
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
  server.stop(true);
  console.log(out.join("\n"));
  const ok =
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

  for await (const [space, message] of app.messages) {
    if (message.direction === "outbound") continue;
    const send: Send = (t) => space.send(t);
    if (message.content.type !== "text") {
      send("Text only for now, sorry.").catch((e) => console.error("send failed", e));
      continue;
    }
    // Stable sender: message.sender.id (docs: messages.md "sender"), falling back to the space id.
    const sender = message.sender?.id ?? space.id;
    // Not awaited: one slow order must not block other conversations.
    void bridge(sender, message.content.text, send, (fn) => space.responding(fn));
  }
}
