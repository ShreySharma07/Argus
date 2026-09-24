import { createContext, ReactNode, useContext, useState } from "react";

import type { Role, Route } from "./api";

export const ROLE_LABEL: Record<Role, string> = {
  analyst: "Fraud analyst",
  L1: "Team lead · L1",
  L2: "Fraud manager · L2",
};

/** Mirrors agent/tools/actions.py CAN_APPROVE. */
export function canApprove(role: Role, route: Route) {
  if (route === "auto") return true;
  if (route === "L1") return role === "L1" || role === "L2";
  return role === "L2";
}

const RoleContext = createContext<{ role: Role; setRole: (r: Role) => void }>({
  role: "analyst",
  setRole: () => {},
});

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role>("analyst");
  return <RoleContext.Provider value={{ role, setRole }}>{children}</RoleContext.Provider>;
}

export const useRole = () => useContext(RoleContext);
