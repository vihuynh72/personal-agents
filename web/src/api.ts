// The only place web/ talks to agent/ (agent/api.py).
//
// Set VITE_API_URL (e.g. the Railway URL) to use the real backend. Without it,
// everything is simulated in this browser so the app can be tried without keys:
// accounts and food profiles are kept in localStorage, Google connect is faked,
// and the conversation is scripted in App.tsx.

export const API = (import.meta as any).env?.VITE_API_URL?.replace(/\/$/, "") as string | undefined;
export const SIMULATED = !API;
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Same shape as contracts/models.py GuestProfile.
export type Profile = {
  id: string;
  name: string;
  restrictions: string[]; // diets: vegan, vegetarian, halal…
  allergens: string[]; // safety: peanut, gluten, shellfish…
  cuisines: string[];
  contact: string | null;
  preferences: string[]; // soft: "avoid mushrooms", "organic"…
};

export type Account = { id: string; name: string; email: string; calendar: "connected" | "skipped" | null; profile: Profile | null };

// ---------- local stand-in for the backend's profile store ----------
const KEY = "gathering.accounts";
function readAll(): Record<string, Account> {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; }
}
function writeAll(all: Record<string, Account>) {
  try { localStorage.setItem(KEY, JSON.stringify(all)); } catch { /* private window: works for this visit only */ }
}
export function forgetAccounts() {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}

// Backend ids allow letters, digits and + @ . _ - (agent/profiles.py _SAFE).
export const idFor = (email: string) => email.trim().toLowerCase().replace(/[^a-z0-9+@._-]/g, "").slice(0, 64);

// Sign in: returns the saved account, or a new one that still needs setup.
export async function signIn(name: string, email: string): Promise<Account> {
  const id = idFor(email);
  const saved = readAll()[id];
  let account: Account = saved ?? { id, name, email, calendar: null, profile: null };
  if (API && !account.profile) {
    // GET /profiles/{id}: someone who already texted the agent has a profile on the server.
    const r = await fetch(`${API}/profiles/${encodeURIComponent(id)}`).catch(() => null);
    if (r?.ok) account = { ...account, profile: await r.json() };
  } else {
    await wait(500);
  }
  saveAccount(account);
  return account;
}

export function saveAccount(a: Account) {
  const all = readAll();
  all[a.id] = a;
  writeAll(all);
}

// PUT /profiles/{id}
export async function saveProfile(account: Account, profile: Profile): Promise<Account> {
  if (API) {
    await fetch(`${API}/profiles/${encodeURIComponent(account.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    }).catch(() => null);
  } else {
    await wait(400);
  }
  const next = { ...account, profile };
  saveAccount(next);
  return next;
}

// GET /connect/google?sender={id} redirects to Google's consent screen (read-only),
// and the backend's callback finishes the connection. Simulated without VITE_API_URL.
export function googleConnectUrl(id: string) {
  return API ? `${API}/connect/google?sender=${encodeURIComponent(id)}` : null;
}

// ---------- conversation and payment ----------
// POST /messages {sender, text} -> {reply}   (agent/chat.py)
// Returns null without a backend or on any failure, so the caller can fall back.
export async function sendMessage(sender: string, text: string): Promise<string | null> {
  if (!API) return null;
  try {
    const r = await fetch(`${API}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sender, text }),
    });
    return r.ok ? ((await r.json()).reply as string) : null;
  } catch { return null; }
}

// The backend's order page /cart/{gid} takes the Stripe payment.
// Opens a real Stripe Checkout (test mode) in a new tab and resolves once Stripe reports it paid.
export async function pay(total: number): Promise<{ paid: boolean }> {
  if (!API) { await wait(1200); return { paid: true }; }
  const tab = window.open("", "_blank"); // opened inside the click, so the browser does not block it
  try {
    const r = await fetch(`${API}/pay`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ total }) });
    if (!r.ok) throw new Error("pay");
    const { id, url } = await r.json();
    if (tab) tab.location.href = url; else window.location.href = url;
    for (let i = 0; i < 300; i++) { // up to 10 minutes
      await wait(2000);
      const s = await fetch(`${API}/pay/${id}`).then((x) => x.json()).catch(() => null);
      if (s?.paid) return { paid: true };
      if (tab?.closed && i > 2) { const last = await fetch(`${API}/pay/${id}`).then((x) => x.json()).catch(() => null); return { paid: !!last?.paid }; }
    }
  } catch { tab?.close(); }
  return { paid: false };
}
