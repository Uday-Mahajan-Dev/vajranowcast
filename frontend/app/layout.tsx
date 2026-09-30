import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "VajraNowcast | AI Thunderstorm & Lightning Nowcasting",
  description:
    "Experimental high-resolution AI thunderstorm and lightning nowcasting for India. Predicting heavy convective rainfall and lightning proxies with 0–6 hour lead time.",
  authors: [{ name: "VajraNowcast Team" }],
  keywords: [
    "VajraNowcast",
    "Thunderstorm Nowcasting",
    "Lightning Prediction India",
    "IMD",
    "MoES",
    "AI Weather Nowcast",
  ],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: "#0d9488",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased selection:bg-brand-500/20 selection:text-brand-700 dark:selection:text-brand-300">
        {children}
      </body>
    </html>
  );
}
