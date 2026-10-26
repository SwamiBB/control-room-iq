/**
 * The running order's order, kept still while someone reads it.
 *
 * A card's place is decided when it arrives: by priority among the cards already there, then after them.
 * After that it does not move, whatever updates arrive (a status change, a warning, a re-send), and it only
 * leaves when it is decided. While `frozen` (the pointer is over the list) an arrival is not slotted in above
 * anything: it goes to the bottom, marked pending, so nothing above the pointer reflows. It is still on
 * screen, since its decision clock is already running. Once the list is free, pending cards move once into
 * their place by priority.
 */

export type Slot = { key: string; weight: number };

export function stableOrder(prev: readonly string[], current: readonly Slot[], frozen: boolean,
                            prevPending: readonly string[] = []): { order: string[]; pending: string[] } {
  const weight = new Map(current.map((s) => [s.key, s.weight]));
  const kept = prev.filter((k) => weight.has(k)); // decided cards leave; the rest keep their places
  const fresh = current.filter((s) => !kept.includes(s.key)).map((s) => s.key);
  const waiting = prevPending.filter((k) => kept.includes(k));
  if (frozen) return { order: [...kept, ...fresh], pending: [...waiting, ...fresh] };

  const order = kept.filter((k) => !waiting.includes(k));
  for (const key of [...waiting, ...fresh]) {
    // Before the first card that is less urgent, so a goal routine still lands above routine graphics.
    const w = weight.get(key) ?? Infinity;
    const at = order.findIndex((k) => (weight.get(k) ?? Infinity) > w);
    if (at === -1) order.push(key);
    else order.splice(at, 0, key);
  }
  return { order, pending: [] };
}
