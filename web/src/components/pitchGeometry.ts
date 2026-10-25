/** Pitch size in metres, and the mapping from the event stream's 0-100 coordinates onto it. */

export const W = 105;
export const H = 68;

/** A point in the event stream's frame: 0-100 on both axes, the team on the ball attacking toward x = 100. */
export type PathPoint = [number, number];

/** 0-100 in possession-relative space to pitch metres, rotated 180 degrees for the away side. */
export function place(x: number, y: number, mirror: boolean) {
  const px = mirror ? 100 - x : x;
  const py = mirror ? 100 - y : y;
  return { cx: (px / 100) * W, cy: (py / 100) * H };
}

/**
 * An SVG path through the points in order, or null for fewer than two: one point has no direction, and a
 * line is never drawn from a point the data does not have.
 */
export function pathD(points: readonly PathPoint[] | null | undefined, mirror: boolean): string | null {
  if (!points || points.length < 2) return null;
  return points
    .map(([x, y], i) => {
      const { cx, cy } = place(x, y, mirror);
      return `${i === 0 ? "M" : "L"} ${cx.toFixed(2)} ${cy.toFixed(2)}`;
    })
    .join(" ");
}

/** A well-formed path from untrusted JSON: at least two finite [x, y] pairs, else null. */
export function asPath(value: unknown): PathPoint[] | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  const ok = value.every((p) => Array.isArray(p) && p.length === 2 && p.every((n) => Number.isFinite(n)));
  return ok ? (value as PathPoint[]) : null;
}
