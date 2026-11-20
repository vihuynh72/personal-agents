import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Table, type Seat } from "./components/Table";
import { CHANNEL, CHANNEL_LABEL, DELIVERY, INGREDIENTS, PEOPLE, PRODUCTS, ROLE, SLOTS, money, nameOf, type Need, type Person, type Slot } from "./data";
import { ON_THE_SIDE, RECIPES } from "./recipes";
import { canListen, canSpeak, hush, speak, useListen, useSpeaking } from "./voice";
import * as api from "./api";

// ---------- types ----------
type Card = "guests" | "pickTime" | "slots" | "invite" | "rsvp" | "menu" | "list" | "receipt";
type Msg =
  | { id: number; from: "me"; text: string }
  | { id: number; from: "agent"; text: string }
  | { id: number; from: "friend"; who: string; text: string; via?: string }
  | { id: number; from: "card"; card: Card };
type NewMsg = Msg extends infer M ? (M extends Msg ? Omit<M, "id"> : never) : never;
type Stage = "start" | "guests" | "when" | "pickTime" | "pickSlot" | "invite" | "rsvp" | "resolve" | "list" | "paid";
type Rsvp = { status: "waiting" | "going" | "no" | "suggest"; note?: string; suggest?: Slot };
type Log = { id: number; node: string; who: string; did: string; used: string; simulated?: boolean };

const GUESTS = PEOPLE.filter((p) => p.role === "guest");
const andList = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

// ---------- demo calendars: who is free when (stands in for the calendar agent) ----------
const FREE: Record<string, string[]> = {
  g1: ["sat7", "sun6"],
  g2: ["sat7", "sun6", "fri730"],
  g3: ["sun6", "fri730"],
  g5: ["sat7", "sun6", "fri730"],
  g6: ["sun6"],
};
const AVAIL_LINE: Record<string, string> = {
  g1: "Free Saturday and Sunday evenings.",
  g2: "Free Friday and Sunday evenings, and Saturday after 6.",
  g3: "Busy Saturday. Free Friday evening and Sunday from 5.",
  g5: "Free all weekend.",
  g6: "Away until Sunday morning. Free Sunday evening.",
};
const isFree = (id: string, slot: Slot) => (FREE[id] ?? []).includes(SLOTS[slot.id] ? slot.id : "sat7");

// How each invitee answers an invitation for a given time.
function answer(id: string, slot: Slot): Rsvp {
  if (isFree(id, slot)) return { status: "going" };
  if (id === "g6") return { status: "no", note: "Away that day, back Sunday morning." };
  const alt = ["sun6", "fri730", "sat7"].map((s) => SLOTS[s]).find((s) => s.id !== slot.id && isFree(id, s));
  return alt ? { status: "suggest", suggest: alt, note: `Can't make it then. Could we do ${alt.short}?` } : { status: "no", note: "Can't make it." };
}

// What each friend's agent says about food, built from that person's profile.
function foodLine(p: Person): string {
  if (!p.needs.length) return `Nothing on file for ${p.name}. Happy with whatever you cook.`;
  const parts = p.needs.map((n) => `${n.label.toLowerCase()}${n.kind === "must" ? " (must-have)" : " (preference)"}`);
  let extra = "";
  if (p.id === ROLE.vegan) extra = " That means no meat, dairy, eggs or honey.";
  if (p.id === ROLE.noSpicy) extra = " Chili on the side is fine, as long as it stays out of the food.";
  return `${p.name}: ${parts.join(", ")}.${extra}`;
}

function needText(ns: Need[]) {
  const musts = ns.filter((n) => n.kind === "must").map((n) => n.label.toLowerCase());
  const flex = ns.filter((n) => n.kind === "flex").map((n) => n.label.toLowerCase());
  return [musts.length ? andList(musts) : "", flex.length ? `you'd rather avoid ${andList(flex)}` : ""].filter(Boolean).join(", and ");
}

// Read a day and time out of a sentence like "dinner Saturday at 7".
function timeIn(text: string): Slot | null {
  const t = text.toLowerCase();
  const day = t.match(/\b(mon|tues|wednes|thurs|fri|satur|sun)day\b/)?.[0];
  const at = t.match(/\b(\d{1,2})(:\d{2})?\s*(am|pm)?\b/);
  if (!day) return null;
  if (day === "saturday" && (!at || at[1] === "7")) return SLOTS.sat7;
  if (day === "sunday" && (!at || at[1] === "6")) return SLOTS.sun6;
  if (day === "friday" && at?.[1] === "7") return SLOTS.fri730;
  const cap = day.charAt(0).toUpperCase() + day.slice(1);
  const time = at ? `${at[1]}${at[2] ?? ""} ${(at[3] ?? "pm").toUpperCase()}` : "7 PM";
  return { id: "custom", label: `${cap} at ${time}`, short: `${cap} at ${time}` };
}

// ---------- app ----------
type Props = { user: { name: string }; calendar: boolean; savedNeeds: Need[]; returning: boolean; onEditFood: () => void; onRestart: () => void; onSignOut: () => void };

export function App({ user, calendar, savedNeeds, returning, onEditFood, onRestart, onSignOut }: Props) {
  const HOST = user.name;
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [stage, setStage] = useState<Stage>("start");
  const hostNeeds = savedNeeds;
  const gf = hostNeeds.some((x) => x.kind === "must" && /gluten/i.test(x.label));
  const [invited, setInvited] = useState<string[]>(GUESTS.map((g) => g.id));
  const [slot, setSlot] = useState<Slot | null>(null);
  const [planned, setPlanned] = useState<Slot | null>(null);
  const [rsvp, setRsvp] = useState<Record<string, Rsvp>>({});
  const [proposal, setProposal] = useState<Slot | null>(null);
  const [have, setHave] = useState<string[]>([]);
  const [removed, setRemoved] = useState<string[]>([]);
  const [labelOk, setLabelOk] = useState(false);
  const [paying, setPaying] = useState(false);
  const [veganChange, setVeganChange] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [typing, setTyping] = useState(false);
  const [readAloud, setReadAloud] = useState(true); // the agent talks back unless muted
  const [handsFree, setHandsFree] = useState(false); // mic stays on between turns
  const [draft, setDraft] = useState("");
  const [log, setLog] = useState<Log[]>([]);
  const [showLog, setShowLog] = useState(false);

  const nextId = useRef(1);
  const queue = useRef<{ ms: number; run: () => void }[]>([]);
  const timer = useRef<number | null>(null);
  const stoppedRef = useRef(false);
  const readRef = useRef(false);
  readRef.current = readAloud;
  const rsvpRef = useRef(rsvp);
  rsvpRef.current = rsvp;

  // ---- message queue: agents talk one after another; Stop freezes it ----
  const pump = useCallback(() => {
    if (timer.current || stoppedRef.current) return;
    const next = queue.current.shift();
    if (!next) { setTyping(false); return; }
    setTyping(true);
    timer.current = window.setTimeout(() => { timer.current = null; next.run(); pump(); }, next.ms);
  }, []);
  const push = useCallback((m: NewMsg) => {
    const msg = { ...m, id: nextId.current++ } as Msg;
    setMsgs((x) => [...x, msg]);
    if (readRef.current && msg.from === "agent") speak(msg.text);
    if (readRef.current && msg.from === "friend") {
      const name = nameOf(msg.who);
      speak(msg.text.startsWith(name) ? msg.text : `${name}: ${msg.text}`);
    }
  }, []);
  const say = useCallback((ms: number, m: NewMsg) => { queue.current.push({ ms, run: () => push(m) }); pump(); }, [push, pump]);
  const then = useCallback((ms: number, run: () => void) => { queue.current.push({ ms, run }); pump(); }, [pump]);
  const note = useCallback((e: Omit<Log, "id">) => setLog((l) => [...l, { ...e, id: l.length + 1 }]), []);
  // When the host typed or spoke, their own words are already in the thread,
  // so actions don't add a second "me" line.
  const typed = useRef(false);
  const me = (text: string) => { if (typed.current) return; hush(); push({ from: "me", text }); };

  const greeted = useRef(false);
  useEffect(() => {
    if (greeted.current) return;
    greeted.current = true;
    const food = savedNeeds.length ? needText(savedNeeds) : "eating anything";
    say(400, { from: "agent", text: returning
      ? `Welcome back, ${HOST}. I still have you down as ${food}. What are we planning?`
      : `Hi ${HOST}, I'm your agent. I've saved your food profile: ${food}. What are we planning? Type, or tap the mic and talk.` });
  }, [say]);

  const attendees = useMemo(() => PEOPLE.filter((p) => p.role === "host" || rsvp[p.id]?.status === "going"), [rsvp]);

  // ================= the flow =================

  // 1. Host says they want to host something.
  function startHosting(text: string) {
    const t = timeIn(text);
    setPlanned(t);
    setStage("guests");
    note({ node: "F1", who: "Your agent", did: `Hosting a dinner${t ? ` on ${t.label}` : ""}. Asked who to invite.`, used: "Your request" });
    say(700, { from: "agent", text: `Love it. Who are you inviting?${t ? ` I'll set it for ${t.short}.` : ""}` });
    say(250, { from: "card", card: "guests" });
  }

  // 2. Host picks who to invite.
  function confirmGuests(ids: string[]) {
    setInvited(ids);
    me(`Invite ${andList(ids.map(nameOf))}`);
    if (planned) return showInvite(planned, false);
    setStage("when");
    say(700, { from: "agent", text: "Do you already have a day and time, or should I find one that works for everyone?" });
  }

  // 3a. Host picks the time.
  function chooseFixed() {
    me("I'll pick the day and time");
    setStage("pickTime");
    say(500, { from: "agent", text: "When should it be?" });
    say(200, { from: "card", card: "pickTime" });
  }
  function submitTime(s: Slot) {
    me(s.label);
    showInvite(s, false);
  }

  // 3b. Agent finds a time from everyone's availability.
  function chooseFind() {
    me("Find a time that works for everyone");
    setStage("pickSlot");
    note({ node: "F4", who: "Scheduler", did: "Asked each invitee's agent when they're free this weekend.", used: "Free or busy from shared calendars", simulated: true });
    say(600, { from: "agent", text: calendar ? "On it. Your Google Calendar shows you're free Friday, Saturday and Sunday evenings. Now I'm asking everyone's agent." : "On it. Your calendar isn't connected, so I'll assume your evenings are free. Now I'm asking everyone's agent." });
    invited.forEach((id, i) => say(700 + i * 120, { from: "friend", who: id, text: `${nameOf(id)}: ${AVAIL_LINE[id] ?? "Free most evenings."}` }));
    say(700, { from: "agent", text: "Here are the times that work best. Tap one and I'll send the invitations with it." });
    say(200, { from: "card", card: "slots" });
  }
  function pickSlot(s: Slot) {
    me(s.short);
    showInvite(s, true);
  }

  // 4. The invitation the friends will get.
  function showInvite(s: Slot, agreed: boolean) {
    setSlot(s);
    setStage("invite");
    const byChannel = (["app", "text", "whatsapp"] as const)
      .map((c) => ({ c, names: invited.filter((id) => (CHANNEL[id] ?? "text") === c).map(nameOf) }))
      .filter((x) => x.names.length)
      .map((x, i) => `${andList(x.names)}${i === 0 ? " will get it" : ""} ${x.c === "app" ? "in the app" : x.c === "text" ? "by text" : "on WhatsApp"}`);
    const calNote = agreed ? "That time works for everyone's calendar. " : calendar ? "That's free on your Google Calendar. " : "";
    say(700, { from: "agent", text: `${calNote}Here's the invitation. ${andList(byChannel)}.` });
    say(200, { from: "card", card: "invite" });
  }

  // 5. Send it and collect replies.
  function sendInvites() {
    if (!slot) return;
    me("Send the invitations");
    setStage("rsvp");
    setRsvp(Object.fromEntries(invited.map((id) => [id, { status: "waiting" } as Rsvp])));
    note({ node: "F3", who: "Coordinator", did: `Sent ${invited.length} invitations for ${slot.label}.`, used: invited.map((id) => `${nameOf(id)}: ${CHANNEL_LABEL[CHANNEL[id] ?? "text"].toLowerCase()}`).join(", "), simulated: true });
    say(500, { from: "agent", text: "Sent. Replies will show up here." });
    say(200, { from: "card", card: "rsvp" });
    const answers = Object.fromEntries(invited.map((id) => [id, answer(id, slot)]));
    invited.forEach((id, i) => {
      then(800 + i * 200, () => {
        const a = answers[id];
        setRsvp((r) => ({ ...r, [id]: a }));
        const text = a.status === "going" ? "Going! See you then." : a.note ?? "Can't make it.";
        push({ from: "friend", who: id, via: CHANNEL_LABEL[CHANNEL[id] ?? "text"], text });
        note({ node: "F3", who: `${nameOf(id)}`, did: a.status === "going" ? "Accepted." : a.status === "no" ? `Declined. ${a.note ?? ""}` : `Suggested ${a.suggest?.label}.`, used: `Invitation ${CHANNEL_LABEL[CHANNEL[id] ?? "text"].toLowerCase()}` });
      });
    });
    then(700, () => afterReplies(slot, answers));
  }

  // 6. Everyone has answered: settle the time.
  function afterReplies(s: Slot, answers: Record<string, Rsvp>) {
    const out = invited.filter((id) => answers[id].status !== "going");
    if (!out.length) return lockIn(s, answers);
    // Most-suggested alternative, then check who could make it from their calendars.
    const counts: Record<string, number> = {};
    out.forEach((id) => { const sg = answers[id].suggest; if (sg) counts[sg.id] = (counts[sg.id] ?? 0) + 1; });
    const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0];
    const alt = best ? SLOTS[best] : null;
    const going = invited.filter((id) => answers[id].status === "going");
    const suggesters = out.filter((id) => answers[id].status === "suggest");
    const decliners = out.filter((id) => answers[id].status === "no");
    const whyOut = [
      suggesters.length ? `${andList(suggesters.map(nameOf))} suggested ${alt?.short ?? "another time"}` : "",
      decliners.length ? `${andList(decliners.map(nameOf))} can't make ${s.short}` : "",
    ].filter(Boolean).join(", and ");
    if (!alt) {
      say(600, { from: "agent", text: `${whyOut}. Everyone else is in, so ${s.short} stays.` });
      then(100, () => lockIn(s, answers));
      return;
    }
    const canAlt = invited.filter((id) => isFree(id, alt));
    setProposal(alt);
    setStage("resolve");
    note({ node: "F4", who: "Scheduler", did: `${alt.short} works for ${canAlt.length} of ${invited.length} by their calendars; ${s.short} works for ${going.length}.`, used: "Replies and shared calendars", simulated: true });
    say(800, {
      from: "agent",
      text: `${whyOut}. I checked everyone's calendar: ${alt.short} works for ${canAlt.length === invited.length ? `all ${invited.length}` : `${canAlt.length} of ${invited.length}`}, while ${s.short} works for ${going.length}. Want to move it?`,
    });
  }

  function moveTo(alt: Slot) {
    if (!slot) return;
    me(`Move it to ${alt.short}`);
    const prior = invited.filter((id) => rsvpRef.current[id]?.status === "going");
    setSlot(alt);
    setStage("rsvp");
    note({ node: "F8", who: "You", did: `Moved the dinner to ${alt.label}.`, used: "Scheduler's suggestion" });
    say(600, { from: "agent", text: `Moving it. I'll only ask ${andList(prior.map(nameOf))} to confirm, since they'd already said yes.` });
    const answers: Record<string, Rsvp> = {};
    invited.forEach((id, i) => {
      answers[id] = isFree(id, alt) ? { status: "going" } : { status: "no", note: "Can't make that one either." };
      then(700 + i * 120, () => {
        setRsvp((r) => ({ ...r, [id]: answers[id] }));
        const wasIn = prior.includes(id);
        push({ from: "friend", who: id, via: CHANNEL_LABEL[CHANNEL[id] ?? "text"], text: answers[id].status === "going" ? (wasIn ? `${alt.short} still works.` : `${alt.short} works, I'm in!`) : answers[id].note! });
      });
    });
    then(500, () => lockIn(alt, answers));
  }

  function keep() {
    if (!slot) return;
    me(`Keep ${slot.short}`);
    note({ node: "F8", who: "You", did: `Kept ${slot.label}.`, used: "" });
    const answers = rsvpRef.current;
    const out = invited.filter((id) => answers[id]?.status !== "going");
    setRsvp(Object.fromEntries(invited.map((id) => [id, answers[id]?.status === "going" ? answers[id] : { status: "no" as const, note: "Can't make this time." }])));
    say(600, { from: "agent", text: `Keeping ${slot.short}. I'll let ${andList(out.map(nameOf))} know, and that it'd be great to see them next time.` });
    then(100, () => lockIn(slot, Object.fromEntries(invited.map((id) => [id, answers[id]?.status === "going" ? answers[id] : { status: "no" as const }]))));
  }

  // 7. Time is settled: talk food with the agents of the people coming.
  function lockIn(s: Slot, answers: Record<string, Rsvp>) {
    const coming = GUESTS.filter((g) => answers[g.id]?.status === "going");
    const n = coming.length + 1;
    setSlot(s);
    setStage("list");
    note({ node: "F8", who: "Your agent", did: `Locked in ${s.label} for ${n}. Calendar invites sent.`, used: "All replies", simulated: true });
    say(600, { from: "agent", text: `Locked in: ${s.label}, ${n} of you. ${calendar ? "It's on your Google Calendar, and everyone else got" : "Everyone got"} a calendar invite. Now I'm asking their agents about food.` });
    coming.forEach((g, i) => say(650 + i * 120, { from: "friend", who: g.id, text: foodLine(g) }));
    const conflicts = [
      coming.some((g) => g.id === ROLE.vegan) && `dairy for ${nameOf(ROLE.vegan)}`,
      coming.some((g) => g.id === ROLE.noMushroom) && `mushrooms for ${nameOf(ROLE.noMushroom)}`,
    ].filter(Boolean) as string[];
    then(300, () => note({ node: "F5", who: "Planner", did: `Menu for ${n}: vegan, no mushrooms, no chili in the food.${conflicts.length ? ` Ruled out creamy mushroom pasta (${conflicts.join(", ")}).` : ""}`, used: `${coming.length} food profiles, cooking time, your kitchen` }));
    const mine = hostNeeds.length ? ` It fits you too (${needText(hostNeeds)})${gf ? ", so it uses gluten-free spaghetti and skips the bread" : ""}.` : "";
    say(700, { from: "agent", text: `Let's make this. It works for all ${n} of you${conflicts.length ? `, and skips anything with ${conflicts.join(" or ")}` : ""}.${mine}` });
    say(200, { from: "card", card: "menu" });
    then(200, () => note({ node: "F6", who: "Shopper", did: `Scaled recipes to ${n}, merged duplicates, checked every product's ingredients against everyone coming.`, used: "Product listings from 2 stores" }));
    say(500, { from: "agent", text: "And here's everything you need to buy, with the recipes. Already have something? Tap × or just tell me." });
    say(200, { from: "card", card: "list" });
  }

  // ================= free text =================
  const respond = (text: string) => {
    const t = text.toLowerCase();
    if (stage === "start") {
      if (/(host|dinner|party|plan|event|gather|lunch|brunch|people over|friends over)/.test(t)) return startHosting(text);
      return say(600, { from: "agent", text: "I can plan a dinner or a get-together for you: invites, timing, menu and groceries. Want to host something?" });
    }
    if (stage === "guests") {
      const named = GUESTS.filter((g) => t.includes(g.name.toLowerCase())).map((g) => g.id);
      if (/everyone|all of them|all/.test(t)) return confirmGuests(GUESTS.map((g) => g.id)), undefined;
      if (named.length) return confirmGuests(named);
      return say(500, { from: "agent", text: "Tick the people above, or tell me their names." });
    }
    if (stage === "when" || stage === "pickTime") {
      const s = timeIn(text);
      if (s) return showInvite(s, false);
      if (/(find|works|convenient|everyone|ask|you pick|any)/.test(t)) return chooseFind();
      if (stage === "when") return chooseFixed();
      return say(500, { from: "agent", text: "Pick a date and time above, or tell me, like \"Saturday at 7\"." });
    }
    if (stage === "pickSlot") {
      const s = timeIn(text);
      if (s) return pickSlot(s);
      return say(500, { from: "agent", text: "Tap one of the times above, or tell me which day you'd like." });
    }
    if (stage === "invite") {
      if (/(send|yes|go|ok|looks good)/.test(t)) return sendInvites();
      return say(500, { from: "agent", text: "Say \"send\" or tap Send invitations when it looks right." });
    }
    if (stage === "resolve" && proposal) {
      if (/(move|yes|sure|ok|switch|change)/.test(t)) return moveTo(proposal);
      if (/(keep|no|stay)/.test(t)) return keep();
      return say(500, { from: "agent", text: `Should I move it to ${proposal.short}, or keep ${slot?.short}?` });
    }
    if (stage === "list") {
      if (/vegan/.test(t)) {
        const who = GUESTS.find((g) => t.includes(g.name.toLowerCase())) ?? GUESTS.find((g) => g.id === ROLE.turnsVegan)!;
        setVeganChange(true);
        note({ node: "F5", who: "Planner", did: `${who.name} is now vegan. Every dish already is, so nothing changes.`, used: `${who.name}'s updated profile` });
        return say(900, { from: "agent", text: `Updated ${who.name} to vegan and rechecked every dish. They're already vegan, so the menu and the list stay the same. Nothing extra to buy.` });
      }
      if (/why|mushroom/.test(t)) return say(700, { from: "agent", text: `Creamy mushroom pasta has cream and parmesan, and ${nameOf(ROLE.vegan)} is vegan. It's also built on mushrooms, which ${nameOf(ROLE.noMushroom)} can't have. Both are must-haves, so I never trade them away.` });
      const found = INGREDIENTS.filter((i) => t.includes(i.name.toLowerCase()) || (i.id === "spaghetti" && /pasta/.test(t)) || (i.id === "oil" && /oil/.test(t))).map((i) => i.id);
      if (found.length && /(have|got)/.test(t)) {
        setHave((h) => Array.from(new Set([...h, ...found])));
        note({ node: "F6", who: "Shopper", did: `Took ${andList(found.map((f) => INGREDIENTS.find((i) => i.id === f)!.name.toLowerCase()))} off the list.`, used: "What you told me you have" });
        return say(700, { from: "agent", text: `Done, I took ${andList(found.map((f) => INGREDIENTS.find((i) => i.id === f)!.name.toLowerCase()))} off the list.${found.includes("spaghetti") ? " You'll still need one pack of spaghetti to have enough." : ""}` });
      }
      if (/buy|pay|checkout|order/.test(t)) return say(500, { from: "agent", text: "Tap Pay with Stripe on the list. I'll never buy without that tap." });
      return say(600, { from: "agent", text: "You can remove anything from the list, check a recipe, or tell me what you already have. Tap Pay with Stripe when it looks right." });
    }
    if (stage === "paid") return say(600, { from: "agent", text: "Everything's on its way. After the dinner I'll check in with everyone, so next time I ask fewer questions." });
    say(500, { from: "agent", text: "One moment, I'm still waiting on replies." });
  };

  function send(text: string) {
    const clean = text.trim();
    if (!clean || stopped) return;
    setDraft("");
    api.sendMessage(HOST, clean);
    me(clean);
    typed.current = true;
    try { respond(clean); } finally { typed.current = false; }
  }

  // ---- shopping list, scaled to the number of people coming ----
  const n = attendees.length;
  const lines = useMemo(() => {
    const f = n / 6;
    return INGREDIENTS.flatMap((i) => {
      const base = i.pantry && have.includes(i.id) ? i.qtyIfPantry : i.qtyIfNot;
      const qty = base > 0 ? Math.max(1, Math.ceil(base * f - 0.01)) : 0;
      if (gf && i.id === "ciabatta") return [];
      const product = gf && i.id === "spaghetti" ? PRODUCTS["b-gfpasta"] : PRODUCTS[i.productId!];
      return qty > 0 && i.productId && !removed.includes(i.id) && !(have.includes(i.id) && !i.pantry) ? [{ ing: i, product, qty }] : [];
    });
  }, [have, removed, n, gf]);
  const totals = useMemo(() => {
    const byStore: Record<string, number> = {};
    for (const l of lines) byStore[l.product.source] = (byStore[l.product.source] ?? 0) + l.product.price * l.qty;
    const items = Object.values(byStore).reduce((a, b) => a + b, 0);
    const delivery = Object.keys(byStore).reduce((a, k) => a + (DELIVERY[k] ?? 0), 0);
    return { byStore, items, delivery, total: items + delivery };
  }, [lines]);
  const needsLabel = lines.some((l) => l.ing.id === "mustard") && !labelOk;

  async function pay() {
    setPaying(true);
    note({ node: "F8", who: "You", did: `Tapped Pay with Stripe for ${money(totals.total)}.`, used: "Shopping list" });
    await api.pay(totals.total);
    setPaying(false);
    setStage("paid");
    note({ node: "F7, F9", who: "Checkout", did: "Stripe confirmed the payment. The session matches the list line by line.", used: "Stripe test mode", simulated: true });
    note({ node: "F13", who: "Fulfilment", did: `Placed ${Object.keys(totals.byStore).length} orders, one per store.`, used: "Merchant account", simulated: true });
    say(300, { from: "card", card: "receipt" });
    say(500, { from: "agent", text: `Paid. Everything arrives the day before. Enjoy the dinner!` });
  }

  // ---- stop / resume / restart ----
  function toggleStop() {
    if (!stopped) {
      stoppedRef.current = true;
      if (timer.current) { clearTimeout(timer.current); timer.current = null; }
      hush();
      setHandsFree(false);
      mic.abort();
      setStopped(true);
      setTyping(false);
      note({ node: "Stop", who: "You", did: "Stopped all agents. Nothing is sent or bought.", used: "" });
    } else {
      stoppedRef.current = false;
      setStopped(false);
      note({ node: "Stop", who: "You", did: "Resumed.", used: "" });
      pump();
    }
  }

  // ---- voice ----
  const sendRef = useRef(send);
  sendRef.current = send;
  const onHeard = useCallback((t: string) => sendRef.current(t), []);
  const mic = useListen(onHeard);
  const speaking = useSpeaking();

  // Hands-free: after the agent has finished its turn (nothing queued, nothing
  // being said), open the mic again. It never listens while the agent talks.
  useEffect(() => {
    if (!handsFree || stopped || paying || typing || speaking || mic.listening) return;
    const t = window.setTimeout(() => mic.start(), 400);
    return () => window.clearTimeout(t);
  }, [handsFree, stopped, paying, typing, speaking, mic.listening, mic.start]);
  useEffect(() => { if (mic.error?.startsWith("Microphone access")) setHandsFree(false); }, [mic.error]);

  function toggleMic() {
    if (handsFree) { setHandsFree(false); mic.abort(); return; }
    hush();
    setReadAloud(true);
    setHandsFree(true);
  }

  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs.length, typing]);

  const chips: string[] =
    stage === "start" ? ["I'm hosting a dinner", "Dinner at my place Saturday at 7"]
    : stage === "when" ? ["I'll pick the day and time", "Find a time that works for everyone"]
    : stage === "invite" ? ["Send the invitations"]
    : stage === "resolve" && proposal && slot ? [`Move it to ${proposal.short}`, `Keep ${slot.short}`]
    : stage === "list" ? [
        ...(!veganChange && attendees.some((p) => p.id === ROLE.turnsVegan) ? [`${nameOf(ROLE.turnsVegan)} is vegan now`] : []),
        "I already have pasta and olive oil",
        "Why no mushroom pasta?",
      ]
    : [];
  function chip(c: string) {
    if (stopped) return;
    if (stage === "when") return c.startsWith("Find") ? chooseFind() : chooseFixed();
    if (stage === "invite") return sendInvites();
    if (stage === "resolve" && proposal) return c.startsWith("Move") ? moveTo(proposal) : keep();
    send(c);
  }

  // ================= render =================
  const renderCard = (card: Card): ReactNode => {
    switch (card) {
      case "guests": return <GuestsCard live={stage === "guests"} invited={invited} onConfirm={confirmGuests} />;
      case "pickTime": return <PickTimeCard live={stage === "pickTime"} onPick={submitTime} />;
      case "slots": return <SlotsCard live={stage === "pickSlot"} invited={invited} chosen={slot} onPick={pickSlot} />;
      case "invite": return slot && <InviteCard host={HOST} slot={slot} live={stage === "invite"} invited={invited} onSend={sendInvites} />;
      case "rsvp": return <RsvpCard invited={invited} rsvp={rsvp} slot={slot} />;
      case "menu": return <MenuCard n={n} gf={gf} />;
      case "list": return <ListCard gf={gf} lines={lines} have={have} totals={totals} n={n} paid={stage === "paid"} paying={paying} needsLabel={needsLabel} labelOk={labelOk} stopped={stopped}
        onRemove={(id) => { setRemoved((r) => [...r, id]); note({ node: "F11", who: "You", did: `Removed ${INGREDIENTS.find((i) => i.id === id)?.name}. Saved as a preference.`, used: "" }); }}
        onLabel={() => { setLabelOk(true); note({ node: "F6", who: "You", did: "Checked the Dijon label: no honey. Marked as checked by you, not the agent.", used: "The store listed no ingredients" }); }}
        onPay={pay} />;
      case "receipt": return (
        <div className="card receipt-card">
          <p className="receipt-big">Paid {money(totals.total)}</p>
          <p className="muted">{Object.keys(totals.byStore).length} orders, one per store. Arrives the day before {slot?.short ?? "the dinner"}.</p>
          <p className="fine">Stripe test mode and a simulated store. No real order was placed.</p>
        </div>
      );
    }
  };

  return (
    <div className="app">
      <header className="bar">
        <span className="brand">Gathering</span>
        <div className="bar-actions">
          <button className="who-chip" onClick={onEditFood} title={`Your food profile. ${calendar ? "Google Calendar connected." : "Calendar not connected."}`}><span className="avatar sm">{HOST[0]}</span><span className="long">Food profile</span></button>
          {canSpeak && (
            <button className={`btn ghost small ${readAloud ? "on" : ""}`} aria-pressed={readAloud} onClick={() => { setReadAloud((r) => !r); hush(); }}>
              <span className="long">{readAloud ? "Voice replies on" : "Voice replies off"}</span><span className="short">{readAloud ? "Sound on" : "Muted"}</span>
            </button>
          )}
          <button className="btn ghost small" onClick={() => setShowLog(true)}><span className="long">How I decided</span><span className="short">Steps</span> <span className="count">{log.length}</span></button>
          <button className={`btn small ${stopped ? "primary" : "stop"}`} onClick={toggleStop}>{stopped ? "Resume" : "Stop"}</button>
        </div>
      </header>

      <main className="thread" aria-live="polite">
        {stopped && <p className="banner stop-banner" role="status">All agents are stopped. Nothing is sent or bought until you resume.</p>}
        {msgs.map((m) => {
          if (m.from === "card") return <div key={m.id} className="row-card">{renderCard(m.card)}</div>;
          if (m.from === "me") return <div key={m.id} className="msg me"><p>{m.text}</p></div>;
          if (m.from === "friend") {
            const p = PEOPLE.find((x) => x.id === m.who)!;
            return (
              <div key={m.id} className="msg friend">
                <span className="avatar">{p.name[0]}</span>
                <div>
                  <p className="who">{p.name}'s agent{m.via && <span className="via">replied {m.via.charAt(0).toLowerCase() + m.via.slice(1)}</span>}</p>
                  <p>{m.text}</p>
                </div>
              </div>
            );
          }
          return (
            <div key={m.id} className="msg agent">
              <span className="avatar mine" aria-hidden="true" />
              <div><p className="who">Your agent</p><p>{m.text}</p></div>
            </div>
          );
        })}
        {typing && !stopped && <div className="msg agent typing" aria-label="Agents are working"><span className="avatar mine" aria-hidden="true" /><span className="dots"><i /><i /><i /></span></div>}
        <div ref={end} />
      </main>

      <footer className="composer">
        {!typing && chips.length > 0 && (
          <div className="chips-row">{chips.map((c) => <button key={c} className="chip-btn" disabled={stopped} onClick={() => chip(c)}>{c}</button>)}</div>
        )}
        {mic.error && <p className="fine mic-err">{mic.error}</p>}
        {handsFree && !mic.error && (
          <p className="voice-status" role="status">
            {mic.listening ? "Listening. Go ahead and talk." : speaking ? "Your agent is talking. The mic opens again when it's done." : typing ? "Your agent is thinking…" : "Opening the mic…"}
            {" "}<button className="link-btn" onClick={toggleMic}>End voice</button>
          </p>
        )}
        <form className="compose" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
          {canListen && (
            <button type="button" className={`mic ${handsFree ? "on" : ""} ${mic.listening ? "live" : ""}`} aria-pressed={handsFree} aria-label={handsFree ? "End the voice conversation" : "Start a voice conversation"} title={handsFree ? "Tap to end the voice conversation" : "Tap to talk. The mic stays on until you tap again."} disabled={stopped} onClick={toggleMic}>
              <MicIcon />
            </button>
          )}
          <input className="compose-input" aria-label="Message your agent" placeholder={mic.listening ? "Listening…" : handsFree ? (speaking ? "Your agent is talking…" : "One moment…") : "Type to your agent"} value={mic.listening ? mic.interim : draft} onChange={(e) => setDraft(e.target.value)} disabled={stopped} />
          <button className="btn primary send" type="submit" disabled={!draft.trim() || stopped}>Send</button>
        </form>
        <div className="foot-links">
          <button className="link-btn restart" onClick={() => { hush(); onRestart(); }}>Start over</button>
          <button className="link-btn restart" onClick={() => { hush(); onSignOut(); }}>Sign out</button>
        </div>
      </footer>

      {showLog && <LogDrawer log={log} onClose={() => setShowLog(false)} />}
    </div>
  );
}

// ================= cards =================

function GuestsCard({ live, invited, onConfirm }: { live: boolean; invited: string[]; onConfirm: (ids: string[]) => void }) {
  const [sel, setSel] = useState<string[]>(invited);
  const ids = live ? sel : invited;
  return (
    <div className="card guests-card">
      <ul className="pick-list">
        {GUESTS.map((g) => {
          const on = ids.includes(g.id);
          return (
            <li key={g.id}>
              <label className={`pick ${on ? "on" : ""}`}>
                <input type="checkbox" checked={on} disabled={!live} onChange={() => setSel(on ? sel.filter((x) => x !== g.id) : [...sel, g.id])} />
                <span className="avatar">{g.name[0]}</span>
                <span className="pick-name">{g.name}</span>
                <span className={`via-pill ${CHANNEL[g.id] ?? "text"}`}>{CHANNEL_LABEL[CHANNEL[g.id] ?? "text"]}</span>
              </label>
            </li>
          );
        })}
      </ul>
      {live && <button className="btn primary block" disabled={!sel.length} onClick={() => onConfirm(sel)}>Invite {sel.length} {sel.length === 1 ? "person" : "people"}</button>}
    </div>
  );
}

function PickTimeCard({ live, onPick }: { live: boolean; onPick: (s: Slot) => void }) {
  const [date, setDate] = useState("2026-11-28");
  const [time, setTime] = useState("19:00");
  if (!live) return null; // the chosen time is already in the thread as the host's reply
  function use() {
    const d = new Date(`${date}T${time}`);
    const key = `${date} ${time}`;
    const known = key === "2026-11-28 19:00" ? SLOTS.sat7 : key === "2026-11-29 18:00" ? SLOTS.sun6 : key === "2026-11-27 19:30" ? SLOTS.fri730 : null;
    const label = d.toLocaleString("en-US", { weekday: "long", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).replace(/,([^,]*)$/, " at$1").replace(":00", "");
    onPick(known ?? { id: "custom", label, short: d.toLocaleString("en-US", { weekday: "long", hour: "numeric", minute: "2-digit" }).replace(" ", " at ").replace(":00", "") });
  }
  return (
    <div className="card small-card">
      <div className="time-row">
        <label><span className="field-label">Day</span><input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label><span className="field-label">Time</span><input className="input" type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>
      </div>
      <button className="btn primary block" onClick={use} disabled={!date || !time}>Use this time</button>
    </div>
  );
}

function SlotsCard({ live, invited, chosen, onPick }: { live: boolean; invited: string[]; chosen: Slot | null; onPick: (s: Slot) => void }) {
  const ranked = Object.values(SLOTS)
    .map((s) => ({ s, free: invited.filter((id) => isFree(id, s)) }))
    .sort((a, b) => b.free.length - a.free.length);
  return (
    <div className="card slots-card">
      {ranked.map(({ s, free }, i) => {
        const out = invited.filter((id) => !free.includes(id));
        return (
          <button key={s.id} className={`slot ${chosen?.id === s.id ? "on" : ""}`} disabled={!live} onClick={() => onPick(s)}>
            <span className="slot-main">
              <span className="slot-t">{s.label}</span>
              <span className="slot-who">{out.length ? `${andList(out.map(nameOf))} can't make it` : "Everyone can make it"}</span>
            </span>
            <span className={`slot-count ${free.length === invited.length ? "all" : ""}`}>{free.length} of {invited.length}{i === 0 && <small>Best</small>}</span>
          </button>
        );
      })}
    </div>
  );
}

function InviteCard({ host: HOST, slot, live, invited, onSend }: { host: string; slot: Slot; live: boolean; invited: string[]; onSend: () => void }) {
  return (
    <div className="card invite-card">
      <p className="invite-kicker">{HOST} invited you to dinner</p>
      <p className="invite-when">{slot.label}</p>
      <p className="muted">At {HOST}'s place. {invited.length + 1} people. Your agent will share what you can eat, so the menu works for you.</p>
      <div className="invite-btns" aria-hidden="true">
        <span>Going</span><span>Can't make it</span><span>Suggest another time</span>
      </div>
      {live && <button className="btn primary block" onClick={onSend}>Send invitations</button>}
    </div>
  );
}

function RsvpCard({ invited, rsvp, slot }: { invited: string[]; rsvp: Record<string, Rsvp>; slot: Slot | null }) {
  const going = invited.filter((id) => rsvp[id]?.status === "going").length;
  const seats: Seat[] = [
    { id: "host", name: "You", state: "host" },
    ...invited.map((id) => {
      const st = rsvp[id]?.status ?? "waiting";
      return { id, name: nameOf(id), tag: nameOf(id), state: st === "going" ? ("replied" as const) : st === "no" ? ("flag" as const) : st === "suggest" ? ("suggest" as const) : ("waiting" as const) };
    }),
  ];
  return (
    <div className="card rsvp-card">
      <Table seats={seats} size={280} center={<span className="center-note"><b>{going}</b> of {invited.length}<br />going</span>} />
      <ul className="rsvp-list">
        {invited.map((id) => {
          const r = rsvp[id] ?? { status: "waiting" };
          const label = r.status === "going" ? "Going" : r.status === "no" ? "Can't make it" : r.status === "suggest" ? `Suggested ${r.suggest?.short}` : "Waiting";
          return (
            <li key={id}>
              <span className="pick-name">{nameOf(id)}</span>
              <span className="fine">{CHANNEL_LABEL[CHANNEL[id] ?? "text"]}</span>
              <span className={`rsvp-pill ${r.status}`}>{label}</span>
            </li>
          );
        })}
      </ul>
      {slot && <p className="fine rsvp-for">For {slot.label}</p>}
    </div>
  );
}

function MenuCard({ n, gf }: { n: number; gf: boolean }) {
  return (
    <div className="card menu-card">
      <p className="menu-title">Dinner for {n}</p>
      {["Main", "Side", "Dessert"].map((course) => (
        <div key={course} className="course">
          <p className="course-name">{course}</p>
          {RECIPES.filter((r) => r.course === course && !(gf && r.id === "bread")).map((r) => <p key={r.id} className="dish-name">{gf && r.id === "main" ? "Tomato and chickpea pasta (gluten-free)" : r.name}</p>)}
        </div>
      ))}
      <p className="menu-side">{ON_THE_SIDE}</p>
    </div>
  );
}

type Line = { ing: (typeof INGREDIENTS)[number]; product: (typeof PRODUCTS)[string]; qty: number };

function ListCard(p: {
  gf: boolean; lines: Line[]; have: string[]; totals: { byStore: Record<string, number>; delivery: number; total: number }; n: number;
  paid: boolean; paying: boolean; needsLabel: boolean; labelOk: boolean; stopped: boolean;
  onRemove: (id: string) => void; onLabel: () => void; onPay: () => void;
}) {
  const [tab, setTab] = useState<"list" | "recipes">("list");
  const [open, setOpen] = useState<string | null>("main");
  const stores = Object.keys(p.totals.byStore).sort();
  const pantry = INGREDIENTS.filter((i) => p.have.includes(i.id));
  return (
    <div className="card list-card">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "list"} className={tab === "list" ? "on" : ""} onClick={() => setTab("list")}>To buy</button>
        <button role="tab" aria-selected={tab === "recipes"} className={tab === "recipes" ? "on" : ""} onClick={() => setTab("recipes")}>Recipes</button>
      </div>

      {tab === "list" ? (
        <div className="tab-body">
          {stores.map((st) => (
            <div key={st} className="store">
              <p className="store-h">{st}</p>
              <ul className="items">
                {p.lines.filter((l) => l.product.source === st).map((l) => (
                  <li key={l.ing.id} className={l.ing.id === "mustard" && !p.labelOk ? "flag" : ""}>
                    <span className="item-n">{l.qty} ×</span>
                    <span className="item-main">
                      {l.product.name}
                      <small>{l.product.pack}</small>
                      {l.ing.id === "mustard" && !p.labelOk && (
                        <span className="flag-note">The store doesn't list ingredients. Check it has no honey. <button className="link-btn" disabled={p.paid} onClick={p.onLabel}>I checked</button></span>
                      )}
                      {l.ing.id === "chili" && <span className="side-note">For the side bowl only</span>}
                    </span>
                    <span className="item-price">{money(l.product.price * l.qty)}</span>
                    {!p.paid && <button className="icon-btn" aria-label={`Remove ${l.product.name}`} onClick={() => p.onRemove(l.ing.id)}>×</button>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {pantry.length > 0 && <p className="fine have">Already at home: {pantry.map((i) => i.name.toLowerCase()).join(", ")}.</p>}
          <dl className="sum">
            <div><dt>Delivery <span className="sim">Simulated</span></dt><dd>{money(p.totals.delivery)}</dd></div>
            <div><dt>Tax</dt><dd className="muted">Unknown</dd></div>
            <div className="total"><dt>Total</dt><dd>{money(p.totals.total)}</dd></div>
          </dl>
        </div>
      ) : (
        <div className="tab-body">
          {p.n !== 6 && <p className="fine">Recipes are written for 6. The shopping list is already scaled to {p.n}.</p>}
          {p.gf && <p className="fine">Use gluten-free spaghetti in the pasta. The ciabatta is left out.</p>}
          {RECIPES.filter((r) => !(p.gf && r.id === "bread")).map((r) => (
            <div key={r.id} className={`recipe ${open === r.id ? "open" : ""}`}>
              <button className="recipe-h" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>
                <span>{r.name}</span><small>{r.minutes} min</small>
              </button>
              {open === r.id && (
                <div className="recipe-body">
                  <ul>{r.ingredients.map((x) => <li key={x}>{x}</li>)}</ul>
                  <ol>{r.steps.map((x) => <li key={x}>{x}</li>)}</ol>
                </div>
              )}
            </div>
          ))}
          <p className="fine">{ON_THE_SIDE}</p>
        </div>
      )}

      {!p.paid && (
        <div className="buy">
          <button className="btn primary lg block" disabled={p.paying || p.needsLabel || p.stopped || !p.lines.length} onClick={p.onPay}>
            {p.paying ? "Opening Stripe…" : `Pay with Stripe, ${money(p.totals.total)}`}
          </button>
          <p className="fine">{p.needsLabel ? "Check the mustard label first, or remove it." : "One payment covers every store. Stripe test mode."}</p>
        </div>
      )}
    </div>
  );
}

function LogDrawer({ log, onClose }: { log: Log[]; onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="drawer-back" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="log-h" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <h2 id="log-h">How I decided</h2>
          <button className="icon-btn" aria-label="Close" autoFocus onClick={onClose}>×</button>
        </div>
        <p className="fine">Every step, what it used and what it decided.</p>
        {log.length === 0 ? <p className="muted">Nothing yet. Steps show up here as the agents work.</p> : (
          <ol className="log">
            {log.map((e) => (
              <li key={e.id}>
                <span className="node-id">{e.node}</span>
                <div>
                  <p className="log-who">{e.who} {e.simulated && <span className="sim">Simulated</span>}</p>
                  <p>{e.did}</p>
                  {e.used && <p className="fine">Used: {e.used}</p>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </aside>
    </div>
  );
}

function MicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}
