import { intelChips, type IntelRegister, type MomentMetrics, type NameOf } from "../intel";

/** The match-intelligence numbers for one moment or graphic, as chips. Renders nothing when there are none. */
export default function IntelChips({ metrics, name, register = "analyst" }: { metrics?: MomentMetrics | null; name: NameOf; register?: IntelRegister }) {
  const chips = intelChips(metrics, name, register);
  if (chips.length === 0) return null;
  return (
    <ul className="intel-chips" aria-label="Match intelligence">
      {chips.map((c) => (
        <li key={c.key} className={`chip ${c.tone ?? "info"}`}>
          <span className="chip-label">{c.label}</span>
          <b className="chip-value">{c.value}</b>
        </li>
      ))}
    </ul>
  );
}
