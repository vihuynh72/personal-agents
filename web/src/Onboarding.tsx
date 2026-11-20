import { useState } from "react";
import { Table } from "./components/Table";
import { HOST } from "./data";
import { forgetAccounts, googleConnectUrl, saveAccount, saveProfile, signIn, SIMULATED, type Account, type Profile } from "./api";

// ---------- 1. sign in ----------
export function Login({ onDone }: { onDone: (a: Account) => void }) {
  const [mode, setMode] = useState<"pick" | "email">("pick");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);

  async function go(n: string, e: string) {
    setBusy(true);
    onDone(await signIn(n, e));
  }

  const seats = ["You", "K", "S", "J", "M", "L"].map((n, i) => ({ id: String(i), name: n, state: i === 0 ? ("host" as const) : ("replied" as const) }));

  return (
    <div className="onboard">
      <div className="onboard-card">
        <div className="onboard-art" aria-hidden="true"><Table seats={seats} size={200} /></div>
        <span className="brand">Gathering</span>
        <h1 className="onboard-h">Dinner with friends, minus the group chat.</h1>
        <p className="muted">Your agent invites people, finds a time, learns what everyone can eat and gets the groceries. You just talk to it.</p>

        {mode === "pick" ? (
          <div className="onboard-actions">
            {/* Simulated Google sign-in returns the host from tools/profiles.json. */}
            <button className="btn google lg block" disabled={busy} onClick={() => go(HOST, "host@example.com")}>
              {busy ? "Signing in…" : "Continue with Google"}
            </button>
            <button className="btn ghost lg block" onClick={() => setMode("email")}>Continue with email</button>
          </div>
        ) : (
          <form className="onboard-actions" onSubmit={(e) => { e.preventDefault(); if (name.trim() && email.includes("@")) go(name.trim().split(" ")[0], email.trim()); }}>
            <label><span className="field-label">Your first name</span><input className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" /></label>
            <label><span className="field-label">Email</span><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
            <button className="btn primary lg block" type="submit" disabled={busy || !name.trim() || !email.includes("@")}>{busy ? "Signing in…" : "Continue"}</button>
            <button type="button" className="link-btn center" onClick={() => setMode("pick")}>Back</button>
          </form>
        )}
        <p className="fine center">
          {SIMULATED ? "Demo: sign-in is simulated and remembered in this browser." : "Signed-in accounts are saved on the server."}{" "}
          {SIMULATED && (forgot ? "Saved accounts cleared." : <button className="link-btn" onClick={() => { forgetAccounts(); setForgot(true); }}>Forget saved accounts</button>)}
        </p>
      </div>
    </div>
  );
}

// ---------- 2. connect Google Calendar ----------
const DAYS = ["Thu", "Fri", "Sat", "Sun"];
const BUSY: [number, number, number][] = [[0, 9, 12], [0, 13, 17], [1, 9, 17], [2, 10, 12], [3, 11, 14]];
const HOURS = [8, 10, 12, 14, 16, 18, 20, 22];

export function CalendarConnect({ account, onDone }: { account: Account; onDone: (a: Account) => void }) {
  const [state, setState] = useState<"idle" | "connecting" | "done">("idle");

  function connect() {
    const url = googleConnectUrl(account.id);
    if (url) {
      // Real: remember it, then hand over to Google's consent screen via the backend.
      saveAccount({ ...account, calendar: "connected" });
      window.location.href = url;
      return;
    }
    setState("connecting");
    setTimeout(() => setState("done"), 1100);
  }
  const finish = (calendar: Account["calendar"]) => {
    const a = { ...account, calendar };
    saveAccount(a);
    onDone(a);
  };

  return (
    <div className="onboard">
      <div className="onboard-card wide">
        <p className="step-note">Step 1 of 2</p>
        <h1 className="onboard-h">Connect your Google Calendar, {account.name}</h1>
        <p className="muted">So your agent can find a time that works for you and your friends, and put the dinner on your calendar once it's set.</p>

        <div className="cal" aria-label="Preview of your week: grey is busy, the rest is free">
          <div className="cal-hours" aria-hidden="true">{HOURS.map((h) => <span key={h} style={{ top: `${((h - 8) / 15) * 100}%` }}>{h > 12 ? `${h - 12} PM` : h === 12 ? "12 PM" : `${h} AM`}</span>)}</div>
          {DAYS.map((d, i) => (
            <div key={d} className="cal-day">
              <span className="cal-d">{d}</span>
              <div className="cal-col">
                {state === "done" && BUSY.filter((b) => b[0] === i).map(([, s, e]) => (
                  <span key={s} className="cal-busy" style={{ top: `${((s - 8) / 15) * 100}%`, height: `${((e - s) / 15) * 100}%` }}>Busy</span>
                ))}
                {state === "done" && <span className="cal-free" style={{ top: `${((18 - 8) / 15) * 100}%`, height: `${(4 / 15) * 100}%` }}>Free</span>}
              </div>
            </div>
          ))}
          {state !== "done" && <div className="cal-veil">{state === "connecting" ? "Connecting…" : "Your week shows up here"}</div>}
        </div>

        <ul className="promise-list">
          <li><b>Only free or busy.</b> Never event names, guests, places or notes.</li>
          <li><b>Your friends' agents do the same</b> with their own calendars, so no one sees anyone else's schedule.</li>
          <li><b>Anyone who hasn't connected counts as "not sure yet",</b> never as free.</li>
        </ul>

        <div className="onboard-actions">
          {state === "done" ? (
            <>
              <p className="good-line">Connected. Your evenings this weekend look free.</p>
              <button className="btn primary lg block" onClick={() => finish("connected")}>Continue</button>
            </>
          ) : (
            <>
              <button className="btn google lg block" disabled={state === "connecting"} onClick={connect}>
                {state === "connecting" ? "Connecting…" : "Connect Google Calendar"}
              </button>
              <button className="link-btn center" onClick={() => finish("skipped")}>Skip for now</button>
            </>
          )}
        </div>
        <p className="fine center">{SIMULATED ? "Demo: the connection is simulated." : "You'll go to Google to approve read-only access, then come back here."}</p>
      </div>
    </div>
  );
}

// ---------- 3. what you can't eat ----------
const ALLERGENS = ["Peanut", "Tree nut", "Egg", "Dairy", "Gluten", "Shellfish", "Fish", "Soy", "Sesame"];
const DIETS = ["Vegan", "Vegetarian", "Pescatarian", "Halal", "Kosher", "No spicy food"];
const AVOID = ["Mushrooms", "Olives", "Cilantro", "Raw onion", "Very sweet", "Seafood"];

export function FoodSetup({ account, onDone, editing = false, onCancel }: { account: Account; onDone: (a: Account) => void; editing?: boolean; onCancel?: () => void }) {
  const p = account.profile;
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
  const [allergens, setAllergens] = useState<string[]>(p?.allergens.map(cap) ?? []);
  const [diets, setDiets] = useState<string[]>(p?.restrictions.map(cap) ?? []);
  const [avoid, setAvoid] = useState<string[]>(p?.preferences.filter((x) => x.startsWith("avoid ")).map((x) => cap(x.slice(6))) ?? []);
  const [other, setOther] = useState("");
  const [busy, setBusy] = useState(false);
  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const nothing = !allergens.length && !diets.length && !avoid.length;

  // Anything typed that isn't a chip goes in as something to avoid.
  function addOther() {
    const v = cap(other.trim());
    if (v && !avoid.includes(v)) setAvoid([...avoid, v]);
    setOther("");
  }

  async function save() {
    setBusy(true);
    const profile: Profile = {
      id: account.id,
      name: account.name,
      allergens: allergens.map((x) => x.toLowerCase()),
      restrictions: diets.map((x) => x.toLowerCase()),
      cuisines: p?.cuisines ?? [],
      contact: p?.contact ?? null,
      preferences: [...(p?.preferences.filter((x) => !x.startsWith("avoid ")) ?? []), ...avoid.map((x) => `avoid ${x.toLowerCase()}`)],
    };
    onDone(await saveProfile(account, profile));
  }

  const group = (title: string, hint: string, items: string[], sel: string[], set: (v: string[]) => void, tone: "must" | "flex") => (
    <fieldset className="food-group">
      <legend>{title}</legend>
      <p className="fine">{hint}</p>
      <div className="toggles">
        {Array.from(new Set([...items, ...sel])).map((x) => (
          <button key={x} type="button" aria-pressed={sel.includes(x)} className={`toggle ${tone} ${sel.includes(x) ? "on" : ""}`} onClick={() => toggle(sel, set, x)}>{x}</button>
        ))}
      </div>
    </fieldset>
  );

  return (
    <div className="onboard">
      <div className="onboard-card wide">
        {!editing && <p className="step-note">Step 2 of 2</p>}
        <h1 className="onboard-h">{editing ? "Your food profile" : "What can't you eat?"}</h1>
        <p className="muted">Your agent shares only this, and only with agents you say yes to, whenever someone invites you or you host. You can change it any time.</p>

        {group("Allergies", "Never in your food. Treated as must-haves.", ALLERGENS, allergens, setAllergens, "must")}
        {group("Diet", "Also must-haves. Never traded away.", DIETS, diets, setDiets, "must")}
        {group("Rather not", "Your agent works around these when it can.", AVOID, avoid, setAvoid, "flex")}

        <form className="other-row" onSubmit={(e) => { e.preventDefault(); addOther(); }}>
          <input className="input" placeholder="Something else you avoid" value={other} onChange={(e) => setOther(e.target.value)} />
          <button className="btn ghost" type="submit" disabled={!other.trim()}>Add</button>
        </form>

        <div className="onboard-actions">
          <button className="btn primary lg block" disabled={busy} onClick={save}>
            {busy ? "Saving…" : nothing ? "I eat everything, continue" : editing ? "Save changes" : "Save and start"}
          </button>
          {editing && onCancel && <button className="link-btn center" onClick={onCancel}>Cancel</button>}
        </div>
        <p className="fine center">This app matches ingredient names. It can't promise a dish is allergy-safe, so allergies are always checked with you and the host.</p>
      </div>
    </div>
  );
}
