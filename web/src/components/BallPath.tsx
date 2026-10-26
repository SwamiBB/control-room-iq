import { useId } from "react";
import { W, pathD, place, type PathPoint } from "./pitchGeometry";

/**
 * Where the ball went, as an ordered list of points: drawn through them in order, the origin marked, an
 * arrowhead at the end. It draws exactly the points it is given and nothing between them, so today's
 * two-point shot and a fuller move trail later go through the same drawing.
 *
 * Draw inside the pitch's <svg>, in its metre coordinates.
 */
export default function BallPath({ points, mirror = false, label, emphasis = "latest", animate = false }: {
  points: readonly PathPoint[];
  /** Rotate 180 degrees: the away side, on a pitch that fixes the home side attacking right. */
  mirror?: boolean;
  label?: string;
  /** "latest" is the bold, labelled one; "past" is a faint line for an earlier shot. */
  emphasis?: "latest" | "past";
  /** Draw the line in once, origin to end. Key the element by the path so a new one animates. */
  animate?: boolean;
}) {
  const arrow = useId().replace(/:/g, "");
  const d = pathD(points, mirror);
  if (!d) return null;
  const start = place(points[0][0], points[0][1], mirror);
  // Above the origin unless that would leave the pitch, and anchored inward near either goal so it stays on it.
  const labelY = start.cy > 6 ? start.cy - 2.6 : start.cy + 4.4;
  const anchor = start.cx > W * 0.8 ? "end" : start.cx < W * 0.2 ? "start" : "middle";

  return (
    <g className={`ball-path ${emphasis} ${animate ? "animate" : ""}`}>
      {emphasis === "latest" && (
        <defs>
          <marker id={arrow} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5"
                  orient="auto-start-reverse" markerUnits="strokeWidth">
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
        </defs>
      )}
      <path className="trail" d={d} pathLength={1} markerEnd={emphasis === "latest" ? `url(#${arrow})` : undefined}>
        {label && <title>{label}</title>}
      </path>
      {emphasis === "latest" && <circle className="origin" cx={start.cx} cy={start.cy} r={0.9} />}
      {emphasis === "latest" && label && (
        <text className="path-label" x={start.cx} y={labelY} textAnchor={anchor}>{label}</text>
      )}
    </g>
  );
}
