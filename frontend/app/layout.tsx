import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SonarCode — Voice Codebase Oracle",
  description:
    "Talk to your GitHub codebase. Ask questions, get standup briefings, and explore code — all by voice.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎙</text></svg>",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#050505] text-gray-100 antialiased">
        {children}
      </body>
    </html>
  );
}
