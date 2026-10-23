import type { MomentMetrics } from "./intel";

export const API = import.meta.env.VITE_API_URL ?? "";
export const WS = API ? API.replace(/^http/, "ws") : `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;

export type Proposal = {
  proposal_id: string; moment_id: string; layer: string; t_start_ms: number; t_end_ms: number;
  line: string; payload: Record<string, unknown>; reasoning: string; priority: number;
  faithfulness: number | null; status: string; decided_by: string | null; override_line: string | null;
};
export type MomentMsg = { moment: { moment_id: string; t_ms: number; period: number; kind: string; importance: number; summary: string; metrics?: MomentMetrics | null };
  explanation: { headline: string; why_it_matters: string; pattern: string; cites: string[]; confidence: number }; line: string; failures: string[];
  intel?: MomentMetrics | null }; // what the agents used: the stats engine's metrics, or what was derived from state

export async function decide(id: string, action: "approve" | "hold" | "override", body: Record<string, unknown> = {}) {
  const r = await fetch(`${API}/proposals/${id}/${action}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ actor: "operator", ...body }) });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Proposal>;
}
export const clock = (ms: number, period: number) => `${String(Math.floor(ms / 60000) + (period === 2 ? 45 : 0)).padStart(2, "0")}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, "0")}`;
