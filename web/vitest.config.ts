import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // tsconfig keeps JSX for Next ("preserve"); the tests compile it with the automatic React runtime.
  oxc: { jsx: { runtime: "automatic" } },
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    environment: "node",
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["node_modules/**", ".next/**"],
  },
});
