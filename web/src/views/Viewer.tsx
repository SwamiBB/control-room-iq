import { useEffect, useState } from "react";
import { WS } from "../api";

const LANGS = { en: "English", es: "Español", hi: "हिन्दी", ar: "العربية" } as const;

export default function Viewer() {
  const [persona, setPersona] = useState<"analyst" | "fan" | "accessibility">("fan");
  const [lang, setLang] = useState<keyof typeof LANGS>("en");
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    const s = new WebSocket(`${WS}/ws/viewer?persona=${persona}&lang=${lang}`);
    s.onmessage = (e) => { const m = JSON.parse(e.data); if (m.type === "overlay") setItems((x) => [m.item, ...x].slice(0, 8)); };
    return () => s.close();
  }, [persona, lang]);

  const current = items[0];
  return (
    <div className={`viewer ${lang === "ar" ? "rtl" : ""}`} dir={lang === "ar" ? "rtl" : "ltr"}>
      <header>
        <h1>Viewer</h1>
        <select value={persona} onChange={(e) => setPersona(e.target.value as any)}>
          <option value="fan">Fan</option><option value="analyst">Analyst</option><option value="accessibility">Audio description</option>
        </select>
        <select value={lang} onChange={(e) => setLang(e.target.value as any)}>
          {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </header>
      <div className="pitch">{current && <div className={`overlay ${current.layer}`}>{current.line}</div>}</div>
      <ul className="history">{items.slice(1).map((i) => <li key={i.item_id}>{i.line}</li>)}</ul>
    </div>
  );
}
