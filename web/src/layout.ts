/**
 * Where each graphics layer sits in the viewer's 16:9 frame, following broadcast convention.
 *
 * Several layers can be on air at once: the goal routine fires a full-screen lead, the scorer's lower third
 * and the score ticker together, the way a real gallery airs them. So every layer has its own region, and
 * any two layers that can be up together never overlap (tested). The one exception is the convention itself:
 * a full-screen graphic takes the middle of the frame, so the side panels and the pitch label wait under it
 * (not dropped; they come back when it ends). The bottom bands and the caption band stay up beside it.
 */

export type Layer =
  | "lower_third" | "stat_panel" | "heatmap" | "ticker" | "full_screen" | "caption" | "player_tag" | "pitch_overlay";

/** Percent of the frame. */
export type Rect = { top: number; left: number; width: number; height: number };

export const LAYER_RECTS: Record<Layer, Rect> = {
  caption: { top: 3, left: 18, width: 64, height: 10 }, // deaf captions: a band at the top, clear of the graphics
  full_screen: { top: 15, left: 14, width: 72, height: 50 }, // centred
  heatmap: { top: 15, left: 3, width: 31, height: 50 }, // a side panel, left
  stat_panel: { top: 15, left: 66, width: 31, height: 50 }, // a side panel, right
  pitch_overlay: { top: 15, left: 36, width: 28, height: 12 }, // a label on the pitch, top centre
  lower_third: { top: 68, left: 3, width: 60, height: 18 }, // the band at bottom left, above the ticker
  player_tag: { top: 70, left: 66, width: 31, height: 10 }, // name and number, bottom right
  ticker: { top: 89, left: 0, width: 100, height: 11 }, // the full-width strip at the very bottom
};

/** Layers that wait under a full-screen graphic rather than share the frame with it. */
export const UNDER_FULL_SCREEN: readonly Layer[] = ["heatmap", "stat_panel", "pitch_overlay"];

export const LAYERS = Object.keys(LAYER_RECTS) as Layer[];

export const layerOf = (layer: string): Layer => (layer in LAYER_RECTS ? (layer as Layer) : "lower_third");

export function overlaps(a: Rect, b: Rect): boolean {
  return a.left < b.left + b.width && b.left < a.left + a.width && a.top < b.top + b.height && b.top < a.top + a.height;
}

/** True when the two layers can be on screen at the same moment. */
export function canShareFrame(a: Layer, b: Layer): boolean {
  if (a === b) return false; // one graphic per layer
  const under = (x: Layer, y: Layer) => x === "full_screen" && UNDER_FULL_SCREEN.includes(y);
  return !under(a, b) && !under(b, a);
}

/**
 * What is on screen, from what is live (newest first): the newest graphic on each layer, minus the layers
 * waiting under a full-screen graphic. A new caption line cuts the running one, as the newest on its layer.
 */
export function onScreen<T extends { packet: { layer: string } }>(live: T[]): T[] {
  const seen = new Set<Layer>();
  const top: T[] = [];
  for (const h of live) {
    const layer = layerOf(h.packet.layer);
    if (seen.has(layer)) continue;
    seen.add(layer);
    top.push(h);
  }
  const fullScreen = seen.has("full_screen");
  return top.filter((h) => !(fullScreen && UNDER_FULL_SCREEN.includes(layerOf(h.packet.layer))));
}

/** The region as inline style for an absolutely positioned overlay. */
export const rectStyle = (r: Rect) => ({ top: `${r.top}%`, left: `${r.left}%`, width: `${r.width}%`, height: `${r.height}%` });
