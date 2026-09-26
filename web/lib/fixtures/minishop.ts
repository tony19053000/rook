// A recorded event log: the full ROOK-023 recorded run on tests/fixtures/minishop (PREPARE -> verified fix
// -> SHIP to a local branch), 369 events, validated against src/rook/core/events.py. Local paths are
// replaced with /workspace. There's no pr.opened: test mode ships to a local branch only.

import { parseEvent, type RookEvent } from "../events";
import raw from "./minishop-run.json";

export const minishopRun: RookEvent[] = (raw as unknown[]).map((value, i) => {
  const event = parseEvent(value);
  if (event === null) throw new Error(`minishop-run.json: event ${i} is not a valid envelope`);
  return event;
});
