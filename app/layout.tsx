import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NTRO // GEO-THERMAL ANOMALY NEXUS",
  description: "Defense-grade tactical GIS command center dashboard for satellite geo-thermal infrastructure monitoring across India.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#090d16] text-slate-200 antialiased overflow-hidden select-none h-screen w-screen">
        {children}
      </body>
    </html>
  );
}
