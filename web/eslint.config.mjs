// ESLint 9 flat config (06 §9): TypeScript, React hooks, Next.js and jsx-a11y. `npm run lint` and `next build`.
import js from "@eslint/js";
import nextPlugin from "@next/eslint-plugin-next";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts", "tsconfig.tsbuildinfo"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // No `files` filter: `next build` looks for the Next plugin in the config it computes for a file.
    plugins: { "@next/next": nextPlugin },
    rules: { ...nextPlugin.configs.recommended.rules, ...nextPlugin.configs["core-web-vitals"].rules },
    settings: { next: { rootDir: "." } },
  },
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks, "jsx-a11y": jsxA11y },
    rules: {
      // The two classic hooks rules (what eslint-config-next enables). eslint-plugin-react-hooks 7's
      // React Compiler rules (purity, set-state-in-effect, …) are left off: the app doesn't use the compiler.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      ...jsxA11y.flatConfigs.recommended.rules,
    },
    languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
  },
  {
    // The e2e scripts are plain Node ESM run outside Next.
    files: ["e2e/**/*.mjs", "*.mjs"],
    languageOptions: {
      globals: {
        process: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        fetch: "readonly",
        URL: "readonly",
        AbortController: "readonly",
        TextDecoder: "readonly",
        Buffer: "readonly",
        WebSocket: "readonly",
      },
    },
  },
);
