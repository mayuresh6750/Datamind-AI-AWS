import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-4xl font-bold tracking-tight">DataMind AI</h1>
      <p className="text-muted-foreground max-w-md text-center">
        Transform raw business data into clean, contextual dashboards — no SQL or Python required.
      </p>
      <div className="flex gap-4">
        <Link
          href="/app"
          className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Open App
        </Link>
        <Link
          href="/admin"
          className="rounded-md border border-input bg-background px-6 py-2 text-sm font-medium hover:bg-accent"
        >
          Admin
        </Link>
      </div>
    </main>
  );
}
