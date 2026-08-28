import Link from "next/link";
import { Compass } from "lucide-react";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-900/40 dark:text-brand-300">
        <Compass size={26} />
      </div>
      <h1 className="mt-5 text-2xl font-black">Page not found</h1>
      <p className="muted mt-2 text-sm">
        That link does not lead anywhere. It may have moved, or never existed.
      </p>
      <Link href="/" className="btn-primary mt-6 inline-flex">
        Back to home
      </Link>
    </div>
  );
}
