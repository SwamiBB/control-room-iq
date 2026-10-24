import { useEffect, useMemo, useState } from "react";
import {
  fetchPreview, fetchViewerGroups, sourceWord,
  type PreviewLine, type ViewerGroup,
} from "../api";
import "./preview.css";

/**
 * "Preview for": what the picked viewer groups would get if this graphic were fired now.
 *
 * Read-only — it builds no packet and logs no decision. It is the only place the post-approval
 * code checks are visible: one approved English line becomes a checked variant for one audience,
 * a template for another and the English line for a third.
 */

type Props = {
  proposalId: string;
  views: string[];
  onChangeViews: (views: string[]) => void;
  /** Typed replacement line; previewed before it is fired, in English, for everyone. */
  overrideLine?: string;
};

const MAX_VIEWS = 12;
const PERSONAS = ["newcomer", "fan", "analyst"] as const;
const ACCESS = ["none", "deaf"] as const;
const LANGS = ["en", "es", "hi"] as const;
const SIDES = ["home", "away", "neutral"] as const;

export default function PreviewFor({ proposalId, views, onChangeViews, overrideLine }: Props) {
  const [lines, setLines] = useState<PreviewLine[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [groups, setGroups] = useState<ViewerGroup[]>([]);
  const [draft, setDraft] = useState({ persona: "fan", access: "none", lang: "es", allegiance: "neutral" });

  // The override is previewed as the operator types, so wait for a pause before asking.
  const [debounced, setDebounced] = useState(overrideLine);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(overrideLine), 400);
    return () => window.clearTimeout(t);
  }, [overrideLine]);

  useEffect(() => {
    if (views.length === 0) { setLines(null); return; }
    let stale = false;
    fetchPreview(proposalId, views, debounced?.trim() || undefined)
      .then((l) => { if (!stale) { setLines(l); setError(null); } })
      .catch(() => { if (!stale) setError("Preview unavailable"); });
    return () => { stale = true; };
  }, [proposalId, views, debounced]);

  useEffect(() => {
    if (picking && groups.length === 0) fetchViewerGroups().then(setGroups).catch(() => undefined);
  }, [picking, groups.length]);

  const draftKey = `${draft.persona}.${draft.access}.${draft.lang}.${draft.allegiance}`;
  const known = useMemo(() => new Set(groups.map((g) => g.key)), [groups]);
  const canAdd = views.length < MAX_VIEWS && !views.includes(draftKey) && (known.size === 0 || known.has(draftKey));

  const label = (key: string) => {
    const [persona, access, lang] = key.split(".");
    return `${lang} ${persona}${access === "deaf" ? " · deaf" : ""}`;
  };

  return (
    <div className="preview-for">
      <div className="preview-head">
        <span className="preview-title">Preview for</span>
        {views.map((v) => (
          <span key={v} className="pick">
            {label(v)}
            <button type="button" aria-label={`Remove ${v}`} onClick={() => onChangeViews(views.filter((x) => x !== v))}>×</button>
          </span>
        ))}
        <button type="button" className="pick-add" onClick={() => setPicking((p) => !p)}>
          {picking ? "Done" : "+ Pick"}
        </button>
      </div>

      {picking && (
        <div className="picker">
          <select value={draft.persona} onChange={(e) => setDraft({ ...draft, persona: e.target.value })} aria-label="Persona">
            {PERSONAS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={draft.access} onChange={(e) => setDraft({ ...draft, access: e.target.value })} aria-label="Access">
            {ACCESS.map((a) => <option key={a} value={a}>{a === "none" ? "standard" : "deaf"}</option>)}
          </select>
          <select value={draft.lang} onChange={(e) => setDraft({ ...draft, lang: e.target.value })} aria-label="Language">
            {LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
          <select value={draft.allegiance} onChange={(e) => setDraft({ ...draft, allegiance: e.target.value })} aria-label="Side">
            {SIDES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button type="button" disabled={!canAdd} onClick={() => onChangeViews([...views, draftKey])}>Add</button>
          {views.length >= MAX_VIEWS && <small>12 is the maximum.</small>}
        </div>
      )}

      {views.length === 0 && <p className="preview-empty">Pick a viewer group to see what it would get.</p>}
      {error && <p className="preview-empty">{error}</p>}

      {lines && lines.length > 0 && (
        <ul className="preview-lines">
          {lines.map((l, i) => (
            <li key={l.key ?? l.view ?? i}>
              <span className="pl-group">{label(l.key ?? l.view ?? views[i] ?? "")}</span>
              <span className="pl-text">{l.text}</span>
              <span className={`pl-source ${l.source}`}>{sourceWord(l.source)}</span>
              {l.failures?.length > 0 && <small className="pl-why">{l.failures.join(", ")}</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
