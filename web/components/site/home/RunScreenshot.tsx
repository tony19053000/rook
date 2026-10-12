import Image from "next/image";
import { Badge } from "../Badge";
import { runScreenshot } from "@/content/home";

// The hero's product figure (06 §5.1): real screenshots of the web app's run page for a recorded guest run
// (captured by e2e/capture-run.mjs), labelled "Recorded example run" (06 §4). A server component; HeroParallax
// only moves the layer it sits in. Phones get the phone capture; wider screens the desktop one with the phone
// capture in front of it.
export function RunScreenshot() {
  const { desktop, mobile } = runScreenshot;
  return (
    <figure data-screenshot className="mx-auto w-full max-w-3xl lg:max-w-5xl 2xl:max-w-6xl">
      <div className="relative sm:pr-10 sm:pb-12 md:pr-14">
        <div className="hidden overflow-hidden rounded-2xl border border-site-line bg-site-card shadow-[0_30px_120px_-40px_rgba(255,106,77,0.45)] sm:block">
          <Image
            src={desktop.src}
            width={desktop.width}
            height={desktop.height}
            alt={desktop.alt}
            sizes="(min-width: 1536px) 1152px, (min-width: 1024px) 1024px, 90vw"
            className="h-auto w-full"
          />
        </div>
        <div className="mx-auto w-[min(17rem,80vw)] overflow-hidden rounded-[1.75rem] border-[6px] border-site-line bg-site-card shadow-[0_24px_80px_-24px_rgba(0,0,0,0.9)] sm:absolute sm:right-0 sm:bottom-0 sm:w-40 md:w-48 lg:w-56 xl:w-64">
          <Image
            src={mobile.src}
            width={mobile.width}
            height={mobile.height}
            alt={mobile.alt}
            sizes="(min-width: 1280px) 256px, (min-width: 640px) 224px, 272px"
            className="h-auto w-full"
          />
        </div>
      </div>
      <figcaption className="mt-5 flex flex-col items-center gap-2 text-center">
        <Badge tone="good">{runScreenshot.label}</Badge>
        <span className="max-w-xl text-sm text-site-muted">{runScreenshot.explanation}</span>
      </figcaption>
    </figure>
  );
}
