"""GET /try: type a phone number, then talk to the real agent in the browser.

It calls the same POST /messages the iMessage bot calls, with the phone number as the sender, so the
conversation, profile, memory and orders are the same ones that person has over text.
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Try the agent</title>
<style>
:root{--bg:#f6f7f4;--fg:#15221c;--mut:#5b6b63;--acc:#1f6f54;--card:#fff;--line:#d9dfd9;--me:#1f6f54;--mefg:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#101613;--fg:#e8efea;--mut:#9aaba2;--acc:#5fc79f;--card:#18211c;--line:#2a362f;--me:#2c8a69;--mefg:#fff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:640px;margin:0 auto;padding:16px;display:flex;flex-direction:column;min-height:100dvh}
h1{font-size:20px;margin:8px 0 2px}p.sub{margin:0 0 12px;color:var(--mut);font-size:14px}
#log{flex:1;display:flex;flex-direction:column;gap:8px;padding:8px 0;overflow-wrap:anywhere}
.b{max-width:88%;padding:10px 12px;border-radius:14px;white-space:pre-wrap;background:var(--card);border:1px solid var(--line)}
.b.me{align-self:flex-end;background:var(--me);color:var(--mefg);border-color:transparent}
.b a{color:inherit;font-weight:600}.b.wait{color:var(--mut);font-style:italic}
form{display:flex;gap:8px;padding:8px 0}input{flex:1;min-width:0;padding:12px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--fg);font:inherit}
button{padding:12px 16px;border-radius:12px;border:0;background:var(--acc);color:#fff;font:inherit;font-weight:600}
button:disabled{opacity:.5}.hint{color:var(--mut);font-size:13px;margin:4px 0 0}
</style></head><body><main>
<h1>Try the agent</h1>
<p class="sub">Enter your phone number, then ask for something. It is the same agent, profile and orders as over text.</p>
<form id="who"><input id="phone" inputmode="tel" autocomplete="tel" placeholder="+1 555 010 1234" aria-label="Phone number" required>
<button>Start</button></form>
<div id="log" aria-live="polite"></div>
<form id="chat" hidden><input id="text" placeholder="get me coffee" aria-label="Message" autocomplete="off" required><button>Send</button></form>
<p class="hint" id="hint" hidden>Try: "get me coffee", "order tacos for dinner", "I want to cook spaghetti", "is this the cheapest?"</p>
</main><script>
let sender = "";
const $ = (id) => document.getElementById(id), log = $("log");
function bubble(text, cls) {
  const d = document.createElement("div"); d.className = "b " + (cls || "");
  for (const part of String(text).split(/(https?:\\/\\/[^\\s]+)/)) {
    if (/^https?:\\/\\//.test(part)) { const a = document.createElement("a"); a.href = part; a.target = "_blank"; a.rel = "noopener"; a.textContent = part.length > 60 ? part.slice(0, 57) + "..." : part; d.append(a); }
    else d.append(document.createTextNode(part));
  }
  log.append(d); d.scrollIntoView({block: "end"}); return d;
}
async function say(text) {
  bubble(text, "me"); const w = bubble("Working on it...", "wait"); $("text").disabled = true;
  try {
    const r = await fetch("/messages", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({sender, text})});
    const j = await r.json(); w.remove(); bubble(r.ok ? j.reply : "Something went wrong: " + (j.detail || r.status));
  } catch (e) { w.remove(); bubble("I could not reach the agent. Try again in a moment."); }
  $("text").disabled = false; $("text").focus();
}
$("who").onsubmit = (e) => {
  e.preventDefault();
  const digits = $("phone").value.replace(/[^0-9+]/g, "");
  if (digits.replace("+", "").length < 10) { $("phone").focus(); return; }
  sender = digits.startsWith("+") ? digits : "+1" + digits.replace(/^1(?=[0-9]{10}$)/, "");
  $("who").hidden = true; $("chat").hidden = false; $("hint").hidden = false;
  bubble("You are " + sender + ". What can I get you?"); $("text").focus();
};
$("chat").onsubmit = (e) => { e.preventDefault(); const t = $("text").value.trim(); if (!t) return; $("text").value = ""; say(t); };
</script></body></html>
"""
