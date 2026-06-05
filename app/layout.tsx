import type { Metadata } from "next";
import { Inter, Inter_Tight, JetBrains_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  weight: ["300", "400", "500", "600", "700"],
});

// Inter Tight is the closest free stand-in for Neue Montreal (tight tracking,
// 500 weight works perfectly for our hero at -0.06em). If you license Neue
// Montreal, swap the family name below — the rest of the design system will
// keep working unchanged.
const neue = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-neue",
  weight: ["300", "400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  weight: ["400", "500", "600"],
});

const instrumentSerif = Instrument_Serif({
  subsets: ["latin"],
  variable: "--font-instrument-serif",
  weight: ["400"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Sentinel — Autonomous Intelligence for Global Markets",
  description:
    "The first autonomous operating system for market research, execution, and portfolio intelligence.",
  icons: {
    icon: "/icon.png",
    apple: "/icon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="icon" href="/icon.png" />
      </head>
      <body
        className={`${inter.variable} ${neue.variable} ${jetbrainsMono.variable} ${instrumentSerif.variable} font-sans antialiased bg-[#030303] text-[#F8F8F8]`}
      >
        {children}
      </body>
    </html>
  );
}
