import "../global.css";
import { Stack } from "expo-router";

import { RoleProvider } from "../lib/role";

export default function RootLayout() {
  return (
    <RoleProvider>
      <Stack screenOptions={{ headerShown: false }} />
    </RoleProvider>
  );
}
