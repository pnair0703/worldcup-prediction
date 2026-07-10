import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Footy Oracle",
  description: "ML-powered soccer match predictions — EPL & World Cup 2026",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
