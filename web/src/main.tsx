import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { CalendarConnect, FoodSetup, Login } from "./Onboarding";
import type { Account, Profile } from "./api";
import type { Need } from "./data";
import "./styles.css";

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

// The saved profile (contracts GuestProfile shape) as the chat's must-haves and soft dislikes.
function needsOf(p: Profile): Need[] {
  return [
    ...p.allergens.map((a) => ({ label: `${cap(a)} allergy`, kind: "must" as const })),
    ...p.restrictions.map((r) => ({ label: cap(r), kind: "must" as const })),
    ...p.preferences.map((x) => ({ label: cap(x.replace(/^avoid /, "")), kind: "flex" as const })),
  ];
}

// First sign-in: connect calendar, then food profile, then chat.
// Later sign-ins with the same account go straight to the chat.
function Root() {
  const [account, setAccount] = useState<Account | null>(null);
  const [returning, setReturning] = useState(false);
  const [editingFood, setEditingFood] = useState(false);
  const [run, setRun] = useState(0);

  if (!account) return <Login onDone={(a) => { setReturning(!!(a.calendar && a.profile)); setAccount(a); }} />;
  if (!account.calendar) return <CalendarConnect account={account} onDone={setAccount} />;
  if (!account.profile) return <FoodSetup account={account} onDone={setAccount} />;
  if (editingFood) return <FoodSetup editing account={account} onCancel={() => setEditingFood(false)} onDone={(a) => { setAccount(a); setEditingFood(false); setRun((r) => r + 1); setReturning(true); }} />;

  return (
    <App
      key={run}
      user={{ name: account.name }}
      calendar={account.calendar === "connected"}
      savedNeeds={needsOf(account.profile)}
      returning={returning}
      onEditFood={() => setEditingFood(true)}
      onRestart={() => { setReturning(true); setRun((r) => r + 1); }}
      onSignOut={() => { setAccount(null); setRun((r) => r + 1); }}
    />
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
