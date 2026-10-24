import Operator from "./Operator";
import Viewer, { type ViewerPreset } from "./Viewer";
import "./multiview.css";

/**
 * One shot for the video: the gallery desktop and three audiences at once.
 *
 * The point of the frame is causality. Every caption on the right appeared because someone fired a
 * graphic on the left, and the three frames show the same approved English line arriving as a checked
 * variant, a template, or the English line, depending on who is watching.
 *
 * Each frame opens its own /ws/viewer connection, exactly as three separate devices would.
 */

const FRAMES: Array<{ id: string; preset: ViewerPreset }> = [
  { id: "a", preset: { persona: "fan", access: "none", lang: "en", allegiance: "neutral" } },
  { id: "b", preset: { persona: "fan", access: "deaf", lang: "es", allegiance: "home" } },
  { id: "c", preset: { persona: "newcomer", access: "deaf", lang: "hi", allegiance: "away" } },
];

export default function Multiview() {
  return (
    <div className="multiview">
      <section className="mv-console">
        <Operator />
      </section>

      <aside className="mv-frames" aria-label="Three viewers watching the same match">
        {FRAMES.map((f) => (
          <div className="mv-frame" key={f.id}>
            <Viewer preset={f.preset} chrome={false} />
          </div>
        ))}
      </aside>
    </div>
  );
}
