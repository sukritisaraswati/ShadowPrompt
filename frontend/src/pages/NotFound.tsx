import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <section className="max-w-xl">
      <h1 className="text-3xl font-bold tracking-tight">Page not found</h1>
      <p className="mt-2 text-slate-600 dark:text-slate-300">
        That route does not exist in ShadowPrompt.
      </p>
      <Link
        to="/"
        className="mt-4 inline-block rounded-md bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600"
      >
        Back to home
      </Link>
    </section>
  );
}
