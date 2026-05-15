import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WiseStamp — Interactive Meeting Backgrounds",
  description: "Animated, brand-personalised video backgrounds for Zoom, Teams and Meet.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
