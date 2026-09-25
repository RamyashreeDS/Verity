import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Verity — Crisis Monitor",
  description: "Self-healing real-time crisis information pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0a0f1e] text-gray-200 antialiased">{children}</body>
    </html>
  );
}
