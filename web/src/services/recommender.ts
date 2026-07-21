import { env } from "../config/env";


export interface RecItem {
  item_id: number;
  title: string;
  type: string;
  category: string;
  description: string;
  topics: string;
  instructor: string;
  platform: string;
  link: string;
  level?: string;
  score?: number;
  tfidf_score?: number;
}

export interface SearchResult {
  results: RecItem[];
  display: string;
  note: string;
  corrected: boolean;
}

export interface ChatResult {
  response: string;
  recommendations: RecItem[];
  intent: string;
}

export interface Persona {
  uid: number;
  label: string;
}

const DEFAULT_TIMEOUT = Number(process.env.RECOMMENDER_TIMEOUT_MS || 60000);
const CHAT_TIMEOUT = Number(process.env.RECOMMENDER_CHAT_TIMEOUT_MS || 240000);

async function call<T>(path: string, init?: RequestInit, timeoutMs = DEFAULT_TIMEOUT): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${env.recommenderUrl}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
    if (!res.ok) {
      throw new Error(`Recommender ${path} -> HTTP ${res.status}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

function post<T>(path: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT): Promise<T> {
  return call<T>(path, { method: "POST", body: JSON.stringify(body) }, timeoutMs);
}

export const recommender = {
  search(query: string, type?: string | null, minPct = 90): Promise<SearchResult> {
    return post<SearchResult>("/api/search", { query, type: type || null, min_pct: minPct });
  },
  chat(message: string, history: { role: string; content: string }[] = []): Promise<ChatResult> {
    return post<ChatResult>("/api/chat", { message, history }, CHAT_TIMEOUT);
  },
  personas(): Promise<Persona[]> {
    return call<Persona[]>("/api/personas");
  },
  forYou(persona: number, interested: number[] = []): Promise<{ recs: RecItem[] }> {
    return post<{ recs: RecItem[] }>("/api/for-you", { persona, interested });
  },
  suggested(): Promise<{ prompts: string[]; welcome: string }> {
    return call<{ prompts: string[]; welcome: string }>("/api/suggested");
  },
};
