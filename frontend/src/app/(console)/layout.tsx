import { AuthGate } from "@/components/auth";
import { Shell } from "@/components/shell";
export default function ConsoleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGate>
      <Shell>{children}</Shell>
    </AuthGate>
  );
}
