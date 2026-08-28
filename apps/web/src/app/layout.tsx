import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { ProfileGate } from "@/components/ProfileGate";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sajilo — Trusted Home Services",
  description:
    "Verified home service professionals in Kathmandu. Fixed transparent pricing, KYC-checked workers, service warranty.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Applies the saved theme before first paint so the page never
            flashes light before switching to dark. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=localStorage.getItem('sajilo.theme');var d=s?s==='dark':matchMedia('(prefers-color-scheme: dark)').matches;if(d)document.documentElement.classList.add('dark')}catch(e){}})()`,
          }}
        />
      </head>
      <body>
        <AuthProvider>
          <Header />
          <ProfileGate />
          <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
          <footer
            className="mt-16 py-8 text-center text-xs muted"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            Sajilo · Kathmandu, Nepal · Every professional is KYC and citizenship verified
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
