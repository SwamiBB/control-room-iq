import { useEffect, useState } from "react";
import { WS } from "../api";
import IntelChips from "../components/IntelChips";
import type { IntelRegister, MomentMetrics } from "../intel";

const LANGS = { en: "English", es: "Español", hi: "हिन्दी" } as const;

export default function Viewer() {
  const [persona, setPersona] = useState<"deaf" | "fan" | "analyst">("deaf");
  const [lang, setLang] = useState<keyof typeof LANGS>("en");
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    const s = new WebSocket(`${WS}/ws/viewer?persona=${persona}&lang=${lang}`);
    s.onmessage = (e) => { const m = JSON.parse(e.data); if (m.type === "overlay") setItems((x) => [m.item, ...x].slice(0, 8)); };
    return () => s.close();
  }, [persona, lang]);

  const current = items[0];
  // The deaf fan gets the fan register: who and where come first in the caption, one number at most here.
  const register: IntelRegister = persona === "analyst" ? "analyst" : "fan";
  const names: Record<string, string> = current?.payload?.intel?.names ?? {}; // set by the agents' code with the intel
  const name = (id?: string | null) => (id ? names[id] ?? id : "");
  return (
    <div className="viewer">
      <header>
        <h1>Viewer</h1>
        <select value={persona} onChange={(e) => setPersona(e.target.value as any)}>
          <option value="deaf">Deaf fan (visual cues + captions)</option><option value="fan">Fan</option><option value="analyst">Analyst</option>
        </select>
        <select value={lang} onChange={(e) => setLang(e.target.value as any)}>
          {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </header>
      <div className="pitch">{current && (
        <div className={`overlay ${current.layer}`}>
          {current.line}
          <IntelChips metrics={current.payload?.intel as MomentMetrics | undefined} name={name} register={register} />
        </div>
      )}</div>
      <ul className="history">{items.slice(1).map((i) => <li key={i.item_id}>{i.line}</li>)}</ul>
    </div>
  );
}
