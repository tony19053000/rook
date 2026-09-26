"use client";

// The canvas agent character (04 §1.3): a 12 x 10 pixel sprite that bounces, blinks and glances while
// working. With prefers-reduced-motion (or `reducedMotion`) it is drawn once, at rest, and never ticks.

import { useEffect, useRef, useState } from "react";
import { useFrame, useReducedMotion } from "@/lib/motion";
import { BOUNCE_PX, drawGrid, HEIGHT, newSeed, pixels, poseAt, REST, WIDTH, type Look } from "@/lib/sprite";

export interface AgentSpriteProps {
  look: Look;
  /** CSS pixels per sprite pixel. */
  px?: number;
  /** Animate at all (a working agent); false draws the rest pose. */
  animate?: boolean;
  /** A shared frame from the parent row; without it the sprite runs its own ticker. */
  frame?: number;
  seed?: number;
  /** Overrides the media query (tests, the dev gallery). */
  reducedMotion?: boolean;
  /** An accessible name; without it the sprite is decorative (the name is shown next to it). */
  label?: string;
}

export function AgentSprite({ look, px = 4, animate = true, frame, seed, reducedMotion, label }: AgentSpriteProps) {
  const mediaReduced = useReducedMotion();
  const reduced = reducedMotion ?? mediaReduced;
  const [ownSeed] = useState(newSeed);
  const ownFrame = useFrame(animate && !reduced && frame === undefined);
  const pose = animate ? poseAt(frame ?? ownFrame, seed ?? ownSeed, reduced) : REST;
  const canvas = useRef<HTMLCanvasElement>(null);

  const { shape, color, eye } = look;
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (ctx) drawGrid(ctx, pixels({ shape, color, eye }, pose.look, pose.blink), 1);
  }, [shape, color, eye, pose.look, pose.blink]);

  return (
    <span
      className="inline-block flex-none"
      data-agent-sprite={shape}
      data-pose={pose.up ? "up" : "rest"}
      data-look={pose.look}
      data-blink={pose.blink ? "1" : "0"}
      data-motion={reduced || !animate ? "static" : "animated"}
      style={{
        transform: pose.up ? `translateY(-${BOUNCE_PX}px)` : undefined,
        transition: reduced ? undefined : "transform 0.18s ease",
      }}
    >
      <canvas
        ref={canvas}
        width={WIDTH}
        height={HEIGHT}
        role={label ? "img" : undefined}
        aria-label={label}
        aria-hidden={label ? undefined : true}
        style={{ width: WIDTH * px, height: HEIGHT * px, imageRendering: "pixelated", display: "block" }}
      />
    </span>
  );
}
