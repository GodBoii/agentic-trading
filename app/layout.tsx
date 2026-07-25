import type { Metadata } from "next";
import {
  IBM_Plex_Mono,
  Instrument_Serif,
  Inter,
  Inter_Tight,
  JetBrains_Mono,
  Manrope,
  Playfair_Display,
  Space_Grotesk,
} from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  weight: ["300", "400", "500", "600", "700"],
});

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

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space",
  weight: ["300", "400", "500", "600", "700"],
});

const playfairDisplay = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-playfair",
  weight: ["400", "500", "600", "700", "800", "900"],
  style: ["normal", "italic"],
});

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
  weight: ["400", "500", "600", "700"],
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-ibm-plex-mono",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Polycognitive — Autonomous Intelligence for Global Markets",
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
        className={`${inter.variable} ${neue.variable} ${jetbrainsMono.variable} ${instrumentSerif.variable} ${spaceGrotesk.variable} ${playfairDisplay.variable} ${manrope.variable} ${ibmPlexMono.variable} font-sans antialiased bg-black text-white`}
      >
        {children}
      </body>
    </html>
  );
}
