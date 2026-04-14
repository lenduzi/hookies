import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hookies — UGC Video Generator",
  description: "Generate polished short-form video cuts from raw footage",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" style={{ height: "100%" }}>
      <body style={{ minHeight: "100%", display: "flex", flexDirection: "column" }}>
        {children}
      </body>
    </html>
  );
}
