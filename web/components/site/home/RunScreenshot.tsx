import Image from "next/image";
import { Badge } from "../Badge";
import { runScreenshot } from "@/content/home";

// The hero's product figure (06 §5.1): real screenshots of the web app's run page for a recorded guest run
// (captured by e2e/capture-run.mjs), labelled "Recorded example run" (06 §4). A server component; HeroParallax
// only moves the layer it sits in. Phones get the phone capture; wider screens the desktop one in a window
// frame, with the phone capture in front of its corner.
export function RunScreenshot() {
  const { desktop, mobile } = runScreenshot;
  return (
    <figure data-screenshot className="mx-auto w-full max-w-3xl lg:max-w-6xl">
      <div className="relative sm:pr-10 sm:pb-12 md:pr-14 lg:pr-16">
        <div className="relative hidden rounded-[1.125rem] border border-site-strong bg-site-card p-1.5 shadow-[inset_0_1px_0_rgb(255_255_255/0.06),0_50px_140px_-40px_rgb(0_0_0/0.95)] sm:block">
          <div aria-hidden className="site-beam absolute inset-x-[22%] -top-px" />
          <div aria-hidden className="flex h-8 items-center gap-1.5 px-2.5">
            <span className="size-2.5 rounded-full bg-site-strong" />
            <span className="size-2.5 rounded-full bg-site-strong" />
            <span className="size-2.5 rounded-full bg-site-strong" />
          </div>
          <div className="overflow-hidden rounded-xl border border-site-line">
            <Image
              src={desktop.src}
              width={desktop.width}
              height={desktop.height}
              alt={desktop.alt}
              sizes="(min-width: 1024px) 1080px, 90vw"
              className="h-auto w-full"
            />
          </div>
        </div>
        <div className="mx-auto w-[min(17rem,80vw)] overflow-hidden rounded-[2rem] border border-site-strong bg-site-card p-1.5 shadow-[inset_0_1px_0_rgb(255_255_255/0.08),0_30px_90px_-20px_rgb(0_0_0/0.95)] sm:absolute sm:right-0 sm:bottom-0 sm:w-40 md:w-48 lg:w-60 xl:w-64">
          <Image
            src={mobile.src}
            width={mobile.width}
            height={mobile.height}
            alt={mobile.alt}
            sizes="(min-width: 1280px) 256px, (min-width: 640px) 240px, 272px"
            className="h-auto w-full rounded-[1.625rem]"
          />
        </div>
      </div>
      <figcaption className="mt-8 flex flex-col items-center gap-x-4 gap-y-2.5 text-center lg:flex-row lg:justify-center lg:text-left">
        <Badge tone="good">{runScreenshot.label}</Badge>
        <span className="max-w-xl text-sm text-site-muted lg:max-w-none">{runScreenshot.explanation}</span>
      </figcaption>
    </figure>
  );
}
