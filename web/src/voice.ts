// Voice in and out using the browser's own speech engines (Chrome, Edge, Safari).
// No key or server needed. If the browser has no speech recognition, the mic
// button is hidden and typing still works.

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
};

// Looked up when the mic opens, not once at load.
const getSR = (): (new () => Recognition) | undefined =>
  typeof window !== "undefined" ? ((window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition) : undefined;

export const canListen = !!getSR();
export const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

// ---------- speaking: a queue, so several replies play in order ----------
let pending = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function speak(text: string) {
  if (!canSpeak) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  pending++;
  emit();
  const done = () => { pending = Math.max(0, pending - 1); emit(); };
  u.onend = done;
  u.onerror = done;
  window.speechSynthesis.speak(u);
}

export function hush() {
  if (!canSpeak) return;
  window.speechSynthesis.cancel();
  pending = 0;
  emit();
}

// True while the agent is talking (or has replies waiting to be spoken).
export function useSpeaking() {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => pending > 0,
  );
}

// ---------- listening: one utterance at a time; the app restarts it for a continuous conversation ----------
export function useListen(onFinal: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const finalText = useRef("");

  const start = useCallback(() => {
    const SR = getSR();
    if (!SR || rec.current) return;
    setError(null);
    finalText.current = "";
    const r = new SR();
    r.lang = "en-US";
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      setInterim(text);
      if (e.results[e.results.length - 1].isFinal) finalText.current = text;
    };
    r.onerror = (e) => {
      // Silence and our own stops are normal in a hands-free conversation.
      if (e.error === "no-speech" || e.error === "aborted") return;
      setError(e.error === "not-allowed" ? "Microphone access is blocked. Allow it in the browser to talk." : "Didn't catch that. Try again or type.");
    };
    r.onend = () => {
      rec.current = null;
      setListening(false);
      setInterim("");
      if (finalText.current.trim()) onFinal(finalText.current.trim());
    };
    rec.current = r;
    try {
      r.start();
      setListening(true);
    } catch {
      rec.current = null;
    }
  }, [onFinal]);

  const stop = useCallback(() => rec.current?.stop(), []);
  const abort = useCallback(() => { rec.current?.abort(); rec.current = null; setListening(false); setInterim(""); }, []);
  useEffect(() => () => rec.current?.abort(), []);
  return { listening, interim, error, start, stop, abort };
}
