// /docs/install (ROOK-055): the detailed install guide. Sources: pyproject.toml (requires-python, the package
// name rook-cli, the two scripts), .github/workflows/ci.yml (tests run on ubuntu-latest), CLAUDE.md §4 (Docker 29,
// Node 24, Bob Shell 2.0.5), src/rook/agents/bob.py (resolve_bin, BOB_API_KEY in the child env, start_new_session),
// src/rook/core/workspace.py (git, ~/.rook/workspaces), src/rook/cli/main.py (--budget, --setup, --sequences,
// --seconds), src/rook/cli/cx.py (ROOK_ENV_<NAME>), src/rook/cli/runs.py (check_loopback), src/rook/cli/github.py,
// 02 §16 (failure modes), 03 §2 (~/.bob-key.env) and 06 §4 (limitations). The install, upgrade, uninstall and
// uvx commands were run against a temporary uv tool folder on 12 Oct 2026.

import { lines, type DocGuide } from "./docsModel";
import { INSTALL_COMMAND, REPO_URL } from "./site";

/** The name in pyproject.toml ([project] name): what uv upgrades and uninstalls. The command is `rook`. */
export const PACKAGE_NAME = "rook-cli";
/** pyproject.toml requires-python is ">=3.12". */
export const PYTHON_MINIMUM = "3.12";
export const BOB_SHELL_DOCS_URL = "https://bob.ibm.com/docs/shell";

export const installGuide: DocGuide = {
  path: "/docs/install",
  navLabel: "Install",
  title: "Install",
  description: "Supported environments, dependencies, IBM Bob Shell and key setup, install, upgrade and uninstall commands, known limitations and troubleshooting.",
  heading: "Install Rook",
  lead: "What Rook needs, how to install, upgrade and remove it, how to set up IBM Bob, and what it cannot do yet.",
  summary: "Supported environments, dependencies, IBM Bob setup, upgrade and uninstall, limitations and troubleshooting.",
  sections: [
    {
      id: "environments",
      title: "Supported environments",
      blocks: [
        {
          kind: "terms",
          items: [
            {
              term: "Operating system",
              text: "Linux. Rook is developed on Linux and its automated tests run on Ubuntu. macOS and Windows (WSL 2 included) have not been tested. Rook uses POSIX process groups and file flags, so native Windows is not expected to work.",
            },
            {
              term: "Python",
              text: `${PYTHON_MINIMUM} or newer (requires-python in pyproject.toml). If you install with uv and have no matching Python, uv fetches one.`,
            },
            {
              term: "Docker",
              text: "A running Docker daemon with the Compose plugin (`docker compose`). The CLI builds and starts your app in a container. Rook is developed against Docker 29; it does not check for a minimum version.",
            },
            { term: "git", text: "Rook copies or clones your repo into a workspace, keeps a baseline commit there and commits the fix to a branch." },
            {
              term: "IBM Bob Shell and Node.js",
              text: "Live runs call IBM Bob through Bob Shell, the `bob` command, which is a Node.js program. Rook is developed with Bob Shell 2.0.5 on Node 24. Rook itself needs no Node.js.",
            },
            { term: "Your app", text: "A backend with an HTTP API, in any language, that can be built and started in Docker." },
          ],
        },
      ],
    },
    {
      id: "install",
      title: "Install",
      blocks: [
        { kind: "code", code: INSTALL_COMMAND, prompt: true },
        {
          kind: "p",
          text: "This installs two commands: `rook`, and rook-pr-comment, which the GitHub Action uses to post its comment. Python packages Rook depends on are installed with it into an environment of its own.",
        },
        {
          kind: "note",
          title: "Not on PyPI",
          text: `Rook is not on PyPI yet, so it installs from GitHub. A package named ${PACKAGE_NAME} exists on PyPI and is a different project: do not install Rook with pip from PyPI.`,
        },
        { kind: "p", text: "There are no release tags yet. To stay on one version, install a commit by its full SHA:" },
        { kind: "code", code: `${INSTALL_COMMAND}@<full-commit-sha>`, prompt: true },
        { kind: "p", text: "To run Rook once without installing it:" },
        { kind: "code", code: `uvx --from git+${REPO_URL} rook --help`, prompt: true },
      ],
    },
    {
      id: "verify",
      title: "Verify the install",
      blocks: [
        { kind: "code", code: lines("rook --version", "rook --help", "docker info", "bob --version") },
        {
          kind: "p",
          text: "The first two show that Rook is installed and on your PATH. `docker info` fails when the Docker daemon is not running, and bob --version shows that Bob Shell is installed. None of them calls IBM Bob.",
        },
      ],
    },
    {
      id: "ibm-bob",
      title: "IBM Bob Shell and your key",
      blocks: [
        {
          kind: "p",
          text: "Bob is the only AI in Rook, and live runs use your own IBM Bob key. Install Bob Shell and get a key from IBM; Rook does not ship either.",
        },
        { kind: "links", items: [{ label: "IBM Bob Shell documentation", href: BOB_SHELL_DOCS_URL, external: true }] },
        {
          kind: "p",
          text: "Rook reads the key from the `BOB_API_KEY` environment variable of the shell that runs it. One way to set it without typing it into your shell history is a small file only you can read:",
        },
        {
          kind: "code",
          label: "~/.bob-key.env (chmod 600)",
          code: "export BOB_API_KEY=<your-key>",
        },
        { kind: "code", code: lines("chmod 600 ~/.bob-key.env", "source ~/.bob-key.env") },
        {
          kind: "list",
          items: [
            "Rook passes the key to Bob Shell only through the child process environment, never as a command-line argument, and scrubs it from its events and logs.",
            "Rook looks for Bob Shell at the path in `ROOK_BOB_BIN` if you set it, then at ~/.nvm/versions/node/v24.21.0/bin/bob, then as bob on your PATH.",
            "Each run has a Bob coin budget: `rook run --budget 1.5` is the default. Once it is spent, Rook refuses further live Bob calls in that run. What your IBM Bob usage costs is between you and IBM.",
            "Never commit the key. In GitHub Actions, store it as a repository secret.",
          ],
        },
        { kind: "links", items: [{ label: "Exactly what is sent to IBM Bob, and when", href: "/docs/data" }] },
      ],
    },
    {
      id: "upgrade-uninstall",
      title: "Upgrade and uninstall",
      blocks: [
        { kind: "p", text: `The package is named ${PACKAGE_NAME}; the command it installs is \`rook\`.` },
        { kind: "code", code: lines(`uv tool upgrade ${PACKAGE_NAME}`, `${INSTALL_COMMAND} --reinstall`, `uv tool uninstall ${PACKAGE_NAME}`) },
        {
          kind: "p",
          text: "The first line asks uv to upgrade the install. If it reports nothing to upgrade and you expected a newer commit, the second line installs again from GitHub. The third removes the commands.",
        },
        {
          kind: "p",
          text: "Uninstalling does not remove Rook's own folder, ~/.rook/: the workspaces of your runs, Bob recordings if you made any, and credentials.json if you signed in. Run `rook logout` first if you signed in, then delete ~/.rook/ yourself.",
        },
      ],
    },
    {
      id: "limitations",
      title: "Known limitations",
      blocks: [
        {
          kind: "list",
          items: [
            "HTTP APIs only: no libraries, pure frontends, mobile apps or ML notebooks.",
            "Rules are checked on what your API returns. State that no HTTP request can read cannot be checked.",
            "Not on PyPI, and no release tags yet: install from GitHub, by commit SHA if you need a fixed version.",
            "Live runs need Docker and your own IBM Bob key.",
            "Tested on Linux only.",
            "The hosted site does not run your own repos: hosted runs of your own repos are turned off. Run them with the CLI on your machine.",
            "The Mapper cannot model every API yet. On two of Rook's own example apps, billing-service and wallet-api, it cannot yet set up actions that depend on other actions, so those two are not offered on the site.",
            "The GitHub Action has not yet been run on a GitHub-hosted runner. See the GitHub Action guide.",
          ],
        },
        {
          kind: "links",
          items: [
            { label: "Roadmap: shipped, limited and planned", href: "/roadmap" },
            { label: "The GitHub Action's limitations", href: "/docs/github-action#limitations" },
          ],
        },
      ],
    },
    {
      id: "troubleshooting",
      title: "Troubleshooting",
      blocks: [
        {
          kind: "terms",
          items: [
            {
              term: "rook: command not found",
              text: "uv's tool folder is not on your PATH. uv prints a warning about it at install time: run uv tool update-shell and open a new terminal.",
            },
            {
              term: "The app won't start",
              text: "The Mechanic tries up to 3 times, reading the app's logs each time. Then Rook asks for a setup value or shows the error. If your app needs a secret or a password to start, pass it with `rook run --setup NAME`, where NAME is an environment variable that holds it.",
            },
            {
              term: "Bob returns an answer Rook can't use",
              text: "Each agent must answer in a fixed JSON shape. Rook asks again with the error, up to 3 attempts, then tells you.",
            },
            {
              term: "An action fails its dry run",
              text: "Rook sends the HTTP response back to the Mapper, up to 3 times. An action that still fails is disabled for the run, and the search goes on without it.",
            },
            {
              term: "A proposed rule disappears",
              text: "A rule that does not hold on a fresh app is rejected as a wrong rule before you see it. The Rules guide explains the one exception.",
            },
            {
              term: "No counterexample found",
              text: "Rook reports that no counterexample was found within the budget. That is not proof the rules hold. Give the search more room with `rook run --sequences 50000 --seconds 300`.",
            },
            {
              term: "A flaky counterexample",
              text: "A sequence that breaks the rule in some replays but not all is shown with its count and marked flaky, and is still reported. Races usually look like this.",
            },
            {
              term: "The fix is not verified",
              text: "When a check fails, Rook goes back to the diagnosis with the new evidence, up to 3 times, then reports honestly that the fix is not verified. An unverified fix is not shipped.",
            },
            {
              term: "Live Bob calls are refused",
              text: "The run's coin budget is spent. Raise it with `rook run --budget 3`, or look at what the run already found: the engine's results stand without Bob.",
            },
            {
              term: "set ROOK_ENV_NAME",
              text: "`rook replay` and `rook verify` need the values your model reads from the environment. For a model that uses env.ADMIN_PASSWORD, set ROOK_ENV_ADMIN_PASSWORD before you run them.",
            },
            {
              term: "--base-url must be your app on this machine",
              text: "`rook replay` and `rook verify` send requests only to a loopback address such as http://127.0.0.1:8000. Start your app locally and pass that address.",
            },
            {
              term: "GitHub repos need a sign-in",
              text: "`rook run owner/name` needs `rook login` and the Rook GitHub App on that repo. To skip both, clone the repo yourself and run Rook on the folder.",
            },
          ],
        },
      ],
    },
  ],
};
