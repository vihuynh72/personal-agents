import type { ReactNode } from "react";

export type Seat = {
  id: string;
  name: string;
  state: "host" | "waiting" | "replied" | "ok" | "flag" | "suggest";
  tag?: string;
};

// The round dinner table: the one signature element. Each seat is a diner and
// their agent; its fill shows where that agent is.
export function Table({ seats, center, size = 380 }: { seats: Seat[]; center?: ReactNode; size?: number }) {
  const c = size / 2;
  const seatR = size * 0.4;
  const plateR = size * 0.235;
  return (
    <figure className="table-wrap" style={{ width: "100%", maxWidth: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Table with ${seats.length} seats`}>
        <circle cx={c} cy={c} r={size * 0.3} className="tbl-top" />
        <circle cx={c} cy={c} r={size * 0.3 - 8} className="tbl-edge" />
        {seats.map((s, i) => {
          const a = (i / seats.length) * Math.PI * 2 - Math.PI / 2;
          const x = c + Math.cos(a) * seatR;
          const y = c + Math.sin(a) * seatR;
          const px = c + Math.cos(a) * plateR;
          const py = c + Math.sin(a) * plateR;
          return (
            <g key={s.id} className={`seat seat-${s.state}`}>
              <circle cx={px} cy={py} r={size * 0.045} className="plate" />
              <circle cx={px} cy={py} r={size * 0.028} className="plate-in" />
              <circle cx={x} cy={y} r={size * 0.075} className="seat-dot" />
              <text x={x} y={y + 5} textAnchor="middle" className="seat-initial">
                {s.state === "host" ? "You" : s.name[0]}
              </text>
              {s.tag && (
                <text x={x} y={y + size * 0.075 + 16} textAnchor="middle" className="seat-tag">
                  {s.tag}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {center && <div className="table-center">{center}</div>}
    </figure>
  );
}
