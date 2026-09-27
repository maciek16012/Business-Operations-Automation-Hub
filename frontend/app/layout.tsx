import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Business Operations Automation Hub",
  description: "Business process automation admin console",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
