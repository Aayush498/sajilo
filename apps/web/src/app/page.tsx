"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Service } from "@/lib/api";
import { npr, SERVICE_EMOJI } from "@/lib/format";
import { Spinner } from "@/components/ui";

const TRUST = [
  { icon: "🪪", title: "KYC + citizenship verified", body: "Every professional is identity-checked before their first job." },
  { icon: "🏷️", title: "Fixed transparent pricing", body: "You see the exact rupee figure before you book. No surprises." },
  { icon: "🛡️", title: "Service warranty", body: "Something not right? We come back and fix it free." },
  { icon: "⭐", title: "Rated by real customers", body: "Only ratings from completed, paid jobs count." },
];

export default function Home() {
  const [services, setServices] = useState<Service[] | null>(null);

  useEffect(() => {
    api.get<Service[]>("/catalog/services", false).then(setServices).catch(() => setServices([]));
  }, []);

  return (
    <div className="space-y-16">
      <section className="animate-rise pt-6 text-center">
        <span className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700 dark:bg-brand-900/50 dark:text-brand-200">
          <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
          Now serving Kathmandu
        </span>

        <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-black leading-tight tracking-tight sm:text-6xl">
          Trusted home services,{" "}
          <span className="text-brand-600 dark:text-brand-400">made sajilo</span>
        </h1>

        <p className="muted mx-auto mt-4 max-w-xl text-base sm:text-lg">
          Verified cleaners, electricians, plumbers, carpenters and AC technicians.
          Fixed prices, booked in under a minute.
        </p>

        <div className="mt-7 flex justify-center gap-3">
          <Link href="/book" className="btn-primary !px-6 !py-3 text-base">
            Book a service
          </Link>
          <Link href="/orders" className="btn-ghost !px-6 !py-3 text-base">
            My orders
          </Link>
        </div>
      </section>

      <section>
        <h2 className="mb-1 text-2xl font-bold">What we do</h2>
        <p className="muted mb-6 text-sm">Five services at launch. More on the way.</p>

        {services === null ? (
          <Spinner />
        ) : services.length === 0 ? (
          <div className="card p-6 text-sm">
            Could not reach the API. Is the backend running on port 8000?
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {services.map((s, i) => {
              const from = Math.min(...s.packages.map((p) => Number(p.price)));
              return (
                <Link
                  key={s.id}
                  href={`/book?service=${s.slug}`}
                  className="card group animate-rise p-5 transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-lg"
                  style={{ animationDelay: `${i * 50}ms` }}
                >
                  <div className="flex items-start justify-between">
                    <span className="text-3xl">{SERVICE_EMOJI[s.slug] ?? "🛠️"}</span>
                    <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-bold text-brand-700 dark:bg-brand-900/50 dark:text-brand-200">
                      {s.warranty_days}-day warranty
                    </span>
                  </div>
                  <h3 className="mt-3 text-lg font-bold group-hover:text-brand-600 dark:group-hover:text-brand-400">
                    {s.name}
                  </h3>
                  <p className="muted mt-1 line-clamp-2 text-sm">{s.description}</p>
                  <p className="mt-3 text-sm font-semibold">
                    From {npr(from)}
                    <span className="muted font-normal"> · {s.packages.length} options</span>
                  </p>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-1 text-2xl font-bold">Why Sajilo</h2>
        <p className="muted mb-6 text-sm">
          Letting a stranger into your home is a trust problem before it is a booking problem.
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TRUST.map((t) => (
            <div key={t.title} className="card p-5">
              <span className="text-2xl">{t.icon}</span>
              <h3 className="mt-2.5 font-bold">{t.title}</h3>
              <p className="muted mt-1 text-sm">{t.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="card overflow-hidden">
        <div className="grid gap-6 p-8 sm:grid-cols-3">
          {[
            ["1", "Pick a service", "Choose what you need and see the fixed price straight away."],
            ["2", "We dispatch a pro", "A verified, skill-matched professional is assigned to you."],
            ["3", "Pay and rate", "Cash or online. Rate the work, and the job closes."],
          ].map(([n, title, body]) => (
            <div key={n}>
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 font-bold text-white">
                {n}
              </span>
              <h3 className="mt-3 font-bold">{title}</h3>
              <p className="muted mt-1 text-sm">{body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
