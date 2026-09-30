import type { Metadata } from "next";
import "./globals.css";
import AuthGate from "./auth-gate";

export const metadata: Metadata = {
  title: "Business Operations Automation Hub",
  description: "Business process automation admin console",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><AuthGate>{children}</AuthGate></body>
    </html>
  );
}
