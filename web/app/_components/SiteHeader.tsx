import Link from "next/link";

/** Shared header used on every page so navigation + branding stay
 * consistent. The WiseStamp logo SVG is hotlinked from their CDN —
 * we don't ship it in the repo since their CDN handles caching +
 * stability for us. */
export function SiteHeader({
  pageBadge,
  rightSlot,
}: {
  /** Small badge next to the logo on each page (e.g. "Meeting Backgrounds Studio"). */
  pageBadge?: string;
  /** Right-aligned navigation slot — each page passes its own links/buttons. */
  rightSlot?: React.ReactNode;
}) {
  return (
    <header className="mb-8 flex items-center justify-between gap-4 border-b border-slate-200/70 pb-5">
      <Link href="/" className="flex items-center gap-3">
        {/* WiseStamp ships only a white-wordmark logo variant (designed for
            dark backgrounds). We wrap it in a dark pill so the wordmark
            stays legible against our light theme — reads as an intentional
            brand badge rather than a workaround. */}
        <span className="inline-flex items-center rounded-lg bg-slate-900 px-3 py-1.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="https://cdn-ildceij.nitrocdn.com/DRnNUxiqxHnxDRbzoFypjebKFRSlJIyA/assets/images/optimized/rev-6a6c5b9/www.wisestamp.com/wp-content/themes/wisestamp/assets/images/wisestamp-logo-light.svg"
            alt="WiseStamp"
            className="h-5 w-auto"
          />
        </span>
        {pageBadge && (
          <span className="hidden rounded-full bg-[#055bfb]/10 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-[#055bfb] sm:inline">
            {pageBadge}
          </span>
        )}
      </Link>
      {rightSlot && <div className="flex items-center gap-2">{rightSlot}</div>}
    </header>
  );
}
