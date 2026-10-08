import Link from "next/link";
import Navbar from "@/components/Navbar";

export default function CampaignsPage() {
  return (
    <main className="min-h-screen bg-black text-white">
      <div className="mx-auto max-w-5xl px-6 py-16">
        <Navbar />

        <p className="text-sm uppercase tracking-[0.3em] text-zinc-500">
          Portfolio Intelligence
        </p>

        <h1 className="mt-3 text-5xl font-bold">
          Campaigns
        </h1>

        <p className="mt-4 max-w-2xl text-lg text-zinc-400">
          Detect coordinated and near-duplicate stock-tip activity.
        </p>

        <div className="mt-10 rounded-2xl border border-zinc-800 bg-zinc-950 p-8">
          <h2 className="text-2xl font-semibold">
            Campaign Intelligence
          </h2>

          <p className="mt-3 text-zinc-500">
            The campaign graph and replay data will be connected to the
            Dakota API in the next step.
          </p>
        </div>

        <Link
          href="/"
          className="mt-8 inline-block rounded-xl bg-white px-5 py-3 font-semibold text-black transition hover:bg-zinc-200"
        >
          Back to Tip Check
        </Link>
      </div>
    </main>
  );
}