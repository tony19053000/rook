import { ImageResponse } from "next/og";
import { ROOK_PATH } from "@/components/site/Logo";
import { metadataCopy, site } from "@/content/site";

// The Open Graph / Twitter card image (06 §8): dark, the logo and the one-liner. Rendered by next/og with its
// built-in font, so nothing is fetched.
export const alt = metadataCopy.ogAlt;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 80px",
          background: "#09090b",
          backgroundImage: "radial-gradient(circle at 85% 0%, rgba(255,106,77,0.22), rgba(9,9,11,0) 55%)",
          color: "#f4f4f5",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <svg width="88" height="88" viewBox="0 0 32 32">
            <rect x="0.5" y="0.5" width="31" height="31" rx="8" fill="#131316" stroke="#34343b" />
            <path fill="#ff6a4d" d={ROOK_PATH} />
          </svg>
          <div style={{ fontSize: 64, fontWeight: 700, letterSpacing: "-0.03em" }}>{site.name}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          <div style={{ fontSize: 52, fontWeight: 700, lineHeight: 1.1, letterSpacing: "-0.03em", maxWidth: 1000 }}>{site.tagline}</div>
          <div style={{ fontSize: 26, lineHeight: 1.45, color: "#a1a1aa", maxWidth: 1000 }}>{`${site.oneLiner} ${site.builtOn}`}</div>
        </div>
      </div>
    ),
    size,
  );
}
