import { useMemo, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  SimulationLinkDatum,
  SimulationNodeDatum,
} from "d3-force";

import type { GraphData, GraphNode } from "../lib/api";

const W = 1100;
const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

const KIND: Record<GraphNode["kind"], { color: string; r: number; name: string }> = {
  case: { color: "#E8ECF4", r: 9, name: "Case" },
  customer: { color: "#6EA8FF", r: 6, name: "Customer" },
  card: { color: "#B69CFF", r: 7, name: "Card" },
  txn: { color: "#F5C451", r: 5, name: "Transaction" },
  device: { color: "#35E0F0", r: 6, name: "Device profile" },
  region: { color: "#8C97AA", r: 4.5, name: "Billing region" },
  linked_card: { color: "#FF6FB5", r: 4.5, name: "Linked card" },
  memory: { color: "#8E9BFF", r: 5, name: "Closed case" },
  pattern: { color: "#FF9F43", r: 7, name: "Pattern" },
};

const VERDICT: Record<string, string> = { fraud: "#FF4D6A", legitimate: "#3EE08F", uncertain: "#F5C451" };

type N = GraphNode & SimulationNodeDatum & { x: number; y: number };
type E = SimulationLinkDatum<N> & { label: string; source: N | string; target: N | string };

function colorOf(n: GraphNode) {
  if (n.kind === "case") return VERDICT[n.props.verdict] ?? KIND.case.color;
  if (n.kind === "txn" && n.props.flagged) return "#FF4D6A";
  if (n.kind === "memory" && n.props.outcome === "cleared") return "#5E6A85";
  return KIND[n.kind].color;
}

function isHot(n: GraphNode) {
  return (n.kind === "case" && n.props.verdict === "fraud") || (n.kind === "txn" && n.props.flagged) ||
    (n.kind === "device" && n.props.shared);
}

export default function GraphCanvas({ data, height = 620, focusId, onOpenCase }: {
  data: GraphData;
  height?: number;
  focusId?: string;
  onOpenCase?: (caseId: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const [selected, setSelected] = useState<N | null>(null);

  const { nodes, edges, neighbors } = useMemo(() => {
    const ns: N[] = data.nodes.map((n, i) => {
      const a = (i / Math.max(data.nodes.length, 1)) * Math.PI * 2;
      return { ...n, x: W / 2 + Math.cos(a) * 200, y: height / 2 + Math.sin(a) * 200 };
    });
    const es: E[] = data.edges.map((e) => ({ ...e }));
    const focus = ns.find((n) => n.id === focusId);
    if (focus) {
      focus.fx = W / 2;
      focus.fy = height / 2;
    }
    const sim = forceSimulation<N>(ns)
      .force("link", forceLink<N, E>(es).id((d) => d.id).distance((l) => {
        const t = (l.target as N).kind;
        return t === "linked_card" || (l.source as N).kind === "linked_card" ? 70 : t === "memory" ? 120 : 95;
      }).strength(0.7))
      .force("charge", forceManyBody().strength(focusId ? -320 : -140))
      .force("center", forceCenter(W / 2, height / 2))
      .force("x", forceX(W / 2).strength(0.04))
      .force("y", forceY(height / 2).strength(0.06))
      .force("collide", forceCollide<N>((d) => KIND[d.kind].r * 3 + 8))
      .stop();
    for (let i = 0; i < 320; i++) sim.tick();
    // Fit the finished layout to the canvas (scale about the centre) instead of clamping nodes to the edges.
    const pad = 46;
    const xs = ns.map((n) => n.x);
    const ys = ns.map((n) => n.y);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const k = Math.min((W - 2 * pad) / Math.max(x1 - x0, 1), (height - 2 * pad) / Math.max(y1 - y0, 1), 1.8);
    const [cx, cy] = [(x0 + x1) / 2, (y0 + y1) / 2];
    for (const n of ns) {
      n.x = W / 2 + (n.x - cx) * k;
      n.y = height / 2 + (n.y - cy) * k;
    }
    const nb = new Map<string, Set<string>>();
    for (const e of es) {
      const s = (e.source as N).id;
      const t = (e.target as N).id;
      if (!nb.has(s)) nb.set(s, new Set());
      if (!nb.has(t)) nb.set(t, new Set());
      nb.get(s)!.add(t);
      nb.get(t)!.add(s);
    }
    return { nodes: ns, edges: es, neighbors: nb };
  }, [data, height, focusId]);

  const active = hover ?? selected?.id ?? null;
  const lit = (id: string) => !active || id === active || neighbors.get(active)?.has(id);
  const kindsPresent = Array.from(new Set(nodes.map((n) => n.kind)));

  return (
    <div style={{ position: "relative", width: "100%", height, background: "#05070C", borderRadius: 10, overflow: "hidden" }}>
      <style>{`
        @keyframes argus-flow { to { stroke-dashoffset: -48; } }
        @keyframes argus-pulse { 0% { transform: scale(1); opacity: .75 } 100% { transform: scale(3.2); opacity: 0 } }
        @keyframes argus-breathe { 0%,100% { opacity: .55 } 50% { opacity: .9 } }
        .argus-flow { stroke-dasharray: 3 13; animation: argus-flow 2.4s linear infinite; }
        .argus-pulse { transform-box: fill-box; transform-origin: center; animation: argus-pulse 2.2s ease-out infinite; }
        .argus-halo { animation: argus-breathe 3.6s ease-in-out infinite; }
        .argus-node { transition: opacity .25s ease; cursor: pointer; }
        .argus-edge { transition: opacity .25s ease; }
      `}</style>
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet"
        onClick={() => setSelected(null)}>
        <defs>
          <pattern id="argus-grid" width="28" height="28" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.9" fill="#141B28" />
          </pattern>
          <radialGradient id="argus-vignette" cx="50%" cy="50%" r="65%">
            <stop offset="0%" stopColor="#0B1220" stopOpacity="1" />
            <stop offset="100%" stopColor="#05070C" stopOpacity="1" />
          </radialGradient>
          <filter id="argus-glow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="3.2" result="b1" />
            <feGaussianBlur in="SourceGraphic" stdDeviation="8" result="b2" />
            <feMerge>
              <feMergeNode in="b2" />
              <feMergeNode in="b1" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="argus-soft" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.2" />
          </filter>
          {Object.entries(KIND).map(([k, v]) => (
            <radialGradient key={k} id={`argus-halo-${k}`}>
              <stop offset="0%" stopColor={v.color} stopOpacity="0.55" />
              <stop offset="100%" stopColor={v.color} stopOpacity="0" />
            </radialGradient>
          ))}
          {Object.entries(VERDICT).map(([k, v]) => (
            <radialGradient key={k} id={`argus-halo-v-${k}`}>
              <stop offset="0%" stopColor={v} stopOpacity="0.6" />
              <stop offset="100%" stopColor={v} stopOpacity="0" />
            </radialGradient>
          ))}
        </defs>
        <rect width={W} height={height} fill="url(#argus-vignette)" />
        <rect width={W} height={height} fill="url(#argus-grid)" />

        {edges.map((e, i) => {
          const s = e.source as N;
          const t = e.target as N;
          const on = !active || s.id === active || t.id === active;
          const hot = isHot(s) || isHot(t);
          const col = colorOf(isHot(t) ? t : s);
          return (
            <g key={i} className="argus-edge" style={{ opacity: on ? 1 : 0.08 }}>
              <line x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke={col} strokeOpacity={active && on ? 0.55 : 0.22} strokeWidth={1} />
              {hot || (active && on) ? (
                <line x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke={col} strokeWidth={1.4} strokeOpacity={0.9}
                  className="argus-flow" filter="url(#argus-soft)" />
              ) : null}
              {active && on ? (
                <text x={(s.x + t.x) / 2} y={(s.y + t.y) / 2 - 4} fill="#6B778C" fontSize={8.5} fontFamily={MONO}
                  textAnchor="middle" letterSpacing={0.6}>{e.label}</text>
              ) : null}
            </g>
          );
        })}

        {nodes.map((n) => {
          const k = KIND[n.kind];
          const col = colorOf(n);
          const r = n.id === focusId ? k.r + 3 : k.r;
          const halo = n.kind === "case" && VERDICT[n.props.verdict] ? `argus-halo-v-${n.props.verdict}` : `argus-halo-${n.kind}`;
          const quiet = focusId ? ["linked_card", "region"] : ["linked_card", "region", "memory", "card"];
          const showLabel = !quiet.includes(n.kind) || (!!active && lit(n.id));
          return (
            <g key={n.id} className="argus-node" style={{ opacity: lit(n.id) ? 1 : 0.12 }}
              onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
              onClick={(ev) => { ev.stopPropagation(); setSelected(n); }}
              onDoubleClick={() => n.kind === "case" && onOpenCase?.(n.label)}>
              <circle cx={n.x} cy={n.y} r={r * 4.2} fill={`url(#${halo})`} className="argus-halo" />
              {isHot(n) ? (
                <circle cx={n.x} cy={n.y} r={r + 2} fill="none" stroke={col} strokeWidth={1} className="argus-pulse" />
              ) : null}
              <circle cx={n.x} cy={n.y} r={r} fill={col} filter="url(#argus-glow)" />
              <circle cx={n.x} cy={n.y} r={r * 0.42} fill="#FFFFFF" opacity={0.85} />
              {showLabel ? (
                <text x={n.x} y={n.y + r + 14} fill={n.kind === "case" ? "#DCE3EE" : "#8491A6"}
                  fontSize={n.kind === "case" ? 11 : 9.5} fontFamily={MONO} textAnchor="middle">
                  {n.label}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>

      <div style={{ position: "absolute", left: 16, bottom: 14, display: "flex", gap: 14, flexWrap: "wrap", maxWidth: "70%" }}>
        {kindsPresent.map((k) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 7, height: 7, borderRadius: 4, background: KIND[k].color, boxShadow: `0 0 8px ${KIND[k].color}` }} />
            <span style={{ color: "#6F7B90", fontSize: 10.5, fontFamily: MONO }}>{KIND[k].name}</span>
          </div>
        ))}
      </div>

      {selected ? (
        <div onClick={(e) => e.stopPropagation()} style={{
          position: "absolute", top: 14, right: 14, width: 270, maxHeight: height - 28, overflowY: "auto",
          background: "rgba(10,14,22,0.82)", backdropFilter: "blur(10px)", border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 10, padding: 16, color: "#DCE3EE", fontFamily: MONO,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: 4, background: colorOf(selected), boxShadow: `0 0 10px ${colorOf(selected)}` }} />
            <span style={{ fontSize: 10.5, letterSpacing: 1.2, textTransform: "uppercase", color: "#7E8AA0" }}>{KIND[selected.kind].name}</span>
          </div>
          <div style={{ fontSize: 13, marginTop: 10, wordBreak: "break-word" }}>{selected.props.full ?? selected.id}</div>
          <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
            {Object.entries(selected.props).filter(([k, v]) => v !== null && v !== undefined && v !== "" && k !== "full")
              .map(([k, v]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 10, fontSize: 11 }}>
                  <span style={{ color: "#6F7B90" }}>{k.replace(/_/g, " ")}</span>
                  <span style={{ color: "#C9D2E0", textAlign: "right", maxWidth: 170, wordBreak: "break-word" }}>{String(v)}</span>
                </div>
              ))}
          </div>
          <div style={{ marginTop: 12, fontSize: 10.5, color: "#5E6A7F" }}>
            {neighbors.get(selected.id)?.size ?? 0} connection(s)
            {selected.kind === "case" && onOpenCase ? " · double-click to open" : ""}
          </div>
        </div>
      ) : null}
    </div>
  );
}
