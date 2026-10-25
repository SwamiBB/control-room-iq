import { useEffect, useRef, useState } from "react";
import type { OperatorSettings } from "../settings";
import "./settings.css";

const SWITCHES: { key: keyof OperatorSettings; label: string; hint: string }[] = [
  { key: "reasoning", label: "Reasoning and evidence", hint: "The producer's reasoning and the cited events on each card." },
  { key: "preview", label: "Preview for", hint: "What each viewer group would see, under each card." },
  { key: "shortcuts", label: "Keyboard shortcuts", hint: "F fire, H hold, D drop, for the card at the top." },
  { key: "alert", label: "Alert on a new graphic", hint: "A chime when a graphic reaches the running order." },
];

/** The operator's four switches, in a popover off the header. Remembered per browser by the caller. */
export default function SettingsMenu({ settings, onChange }: {
  settings: OperatorSettings;
  onChange: (next: OperatorSettings) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div className="settings" ref={root}>
      <button
        className="settings-toggle"
        aria-expanded={open}
        aria-controls="operator-settings"
        onClick={() => setOpen((o) => !o)}
      >
        Settings
      </button>
      {open && (
        <div id="operator-settings" className="settings-panel" role="group" aria-label="Console settings">
          {SWITCHES.map((s) => (
            <label key={s.key}>
              <input
                type="checkbox"
                checked={settings[s.key]}
                onChange={(e) => onChange({ ...settings, [s.key]: e.target.checked })}
              />
              <span>
                <b>{s.label}</b>
                <small>{s.hint}</small>
              </span>
            </label>
          ))}
          <p className="settings-note">Saved in this browser. Every graphic stays on the desk whatever is set here.</p>
        </div>
      )}
    </div>
  );
}
