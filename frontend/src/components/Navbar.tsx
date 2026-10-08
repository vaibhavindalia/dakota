"use client";

import Link from "next/link";

const links = [
  ["Investigate", "/investigate"],
  ["Tip Check", "/"],
  ["Stocks", "/stocks"],
  ["Portfolio", "/portfolio"],
  ["Watcher", "/watcher"],
  ["Campaigns", "/campaigns"],
];

export default function Navbar() {
  return (
    <nav className="sticky top-0 z-50 border-b border-white/10 bg-[#080b12]/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-5 px-6 py-3">
        <Link href="/investigate" className="mr-3 text-lg font-bold tracking-tight text-white">DAKOTA</Link>
        <div className="flex flex-wrap gap-2 text-sm text-white/55">
          {links.map(([label, href]) => (
            <Link key={href} href={href} className="rounded-lg px-3 py-2 transition hover:bg-white/5 hover:text-white">
              {label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
