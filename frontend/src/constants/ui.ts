/** Design tokens for the analyst console. One accent, quiet greys, semantic colour only where it carries meaning. */
export const C = {
  bg: "#F6F7F9",
  panel: "#FFFFFF",
  line: "#E6E8EC",
  lineSoft: "#F0F1F4",
  text: "#0E1116",
  text2: "#5B6472",
  text3: "#8A93A1",
  accent: "#2F5BEA",
  accentSoft: "#EEF2FE",
  fraud: "#C2303A",
  fraudSoft: "#FCEEEF",
  legit: "#1F7A4D",
  legitSoft: "#EAF5EF",
  uncertain: "#B7791F",
  uncertainSoft: "#FBF3E4",
  sidebar: "#0C0F14",
  sidebarLine: "#1C212B",
  sidebarText: "#8B93A3",
};

export const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

export const verdictColor = (v: string) =>
  v === "fraud" ? C.fraud : v === "legitimate" ? C.legit : C.uncertain;
export const verdictSoft = (v: string) =>
  v === "fraud" ? C.fraudSoft : v === "legitimate" ? C.legitSoft : C.uncertainSoft;

export const TRIGGER_LABEL: Record<string, string> = {
  risk_score: "Model score",
  customer_report: "Customer report",
  analyst_request: "Analyst request",
};

export const humanize = (s: string) => (s === "none" ? "—" : s.replace(/_/g, " "));
export const usd = (n: number) =>
  `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
