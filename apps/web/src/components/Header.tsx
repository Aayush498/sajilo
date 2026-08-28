"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { LoginDialog } from "./LoginDialog";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/book", label: "Book" },
  { href: "/orders", label: "My orders" },
  { href: "/worker", label: "Worker" },
  { href: "/admin", label: "Admin" },
];

function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("sajilo.theme");
    const prefers = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const on = saved ? saved === "dark" : prefers;
    setDark(on);
    document.documentElement.classList.toggle("dark", on);
  }, []);

  return (
    <button
      className="btn-ghost !px-2.5 !py-2"
      aria-label="Toggle theme"
      onClick={() => {
        const on = !dark;
        setDark(on);
        document.documentElement.classList.toggle("dark", on);
        localStorage.setItem("sajilo.theme", on ? "dark" : "light");
      }}
    >
      {dark ? "☀️" : "🌙"}
    </button>
  );
}

export function Header() {
  const path = usePathname();
  const { user, ready, logout } = useAuth();
  const [login, setLogin] = useState(false);

  return (
    <>
      <header
        className="sticky top-0 z-40 backdrop-blur-md"
        style={{
          borderBottom: "1px solid var(--border)",
          background: "color-mix(in srgb, var(--surface) 85%, transparent)",
        }}
      >
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-lg font-black text-white">
              S
            </span>
            <span className="hidden sm:block">
              <span className="block text-base font-extrabold leading-none">Sajilo</span>
              <span className="muted block text-[10px] font-medium tracking-wide">
                Trusted Home Services
              </span>
            </span>
          </Link>

          <nav className="ml-auto hidden items-center gap-1 md:flex">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  path === n.href
                    ? "bg-brand-50 text-brand-700 dark:bg-brand-900/50 dark:text-brand-200"
                    : "hover:bg-brand-50 dark:hover:bg-brand-900/30"
                }`}
              >
                {n.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <ThemeToggle />
            {ready && user ? (
              <div className="flex items-center gap-2">
                <div className="hidden text-right sm:block">
                  <p className="text-xs font-semibold leading-tight">
                    {user.full_name ?? user.phone}
                  </p>
                  <p className="muted text-[10px] capitalize leading-tight">{user.role}</p>
                </div>
                <button className="btn-ghost !px-3 !py-2 text-xs" onClick={logout}>
                  Sign out
                </button>
              </div>
            ) : (
              <button className="btn-primary !py-2 text-xs" onClick={() => setLogin(true)}>
                Sign in
              </button>
            )}
          </div>
        </div>

        <nav className="flex gap-1 overflow-x-auto px-4 pb-2 md:hidden">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium ${
                path === n.href
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-900/50 dark:text-brand-200"
                  : "muted"
              }`}
            >
              {n.label}
            </Link>
          ))}
        </nav>
      </header>

      {login && <LoginDialog role="customer" onClose={() => setLogin(false)} />}
    </>
  );
}
