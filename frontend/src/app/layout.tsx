import type { Metadata } from "next";
import { AuthProvider } from "@/components/auth";
import "./globals.css";
export const metadata: Metadata = {
  title: {
    default: "FlowPilot · Operations console",
    template: "%s · FlowPilot",
  },
  description:
    "Vendor onboarding with verifiable evidence, human approvals and an auditable workflow.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
