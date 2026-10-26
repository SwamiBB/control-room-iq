import { homeOf, isKeeper, shirtOf, teamOf, toPitch, type TrackingFrame } from "./tracking";

/**
 * The players and the ball as the tracking stream has them: a dot per player in their side's colour with the shirt
 * number (the keepers in their own colours, as their kits are), the ball sized by its height with a shadow when it is in the air, and a fading trail behind it. Each
 * moves to the next frame over the time the frames are arriving apart, so 4 frames a second read as movement.
 *
 * Draw inside the pitch's <svg>, in its metre coordinates, under the shot path.
 */
export default function TrackingLayer({ frame, trail, homeTeam, stepMs }: {
  frame: TrackingFrame;
  /** Earlier frames, oldest first, for the ball's trail. */
  trail: readonly TrackingFrame[];
  homeTeam?: string;
  /** How long to take moving to this frame: the real time since the last one. */
  stepMs: number;
}) {
  const home = homeOf(frame, homeTeam);
  const move = (cx: number, cy: number) => ({
    transform: `translate(${cx.toFixed(2)}px, ${cy.toFixed(2)}px)`,
    transition: `transform ${stepMs}ms linear`,
  });
  const [bx, by, height] = frame.ball;
  const ball = toPitch(bx, by);
  // The trail runs up to the frame the ball is moving from, so it never runs ahead of the ball.
  const behind = trail.map((f) => toPitch(f.ball[0], f.ball[1])).map((p) => `${p.cx.toFixed(2)},${p.cy.toFixed(2)}`);

  return (
    <g className="tracking" aria-hidden="true">
      {behind.length > 1 && <polyline className="ball-trail" points={behind.join(" ")} />}
      {Object.entries(frame.players).map(([id, [x, y]]) => {
        const { cx, cy } = toPitch(x, y);
        const shirt = shirtOf(id);
        return (
          <g key={id} className={`player ${teamOf(id) === home ? "home" : "away"}${isKeeper(id) ? " keeper" : ""}`}
             style={move(cx, cy)}>
            <circle r={1.25} />
            {shirt != null && <text dy="0.42">{shirt}</text>}
          </g>
        );
      })}
      <g className="ball" style={move(ball.cx, ball.cy)}>
        {/* In the air: the shadow stays on the ground and the ball grows a little with height. */}
        {height > 0.3 && <ellipse className="shadow" cx={height * 0.2} cy={height * 0.3} rx={0.6} ry={0.35} />}
        <circle r={0.6 + Math.min(height, 12) * 0.06} />
      </g>
    </g>
  );
}
