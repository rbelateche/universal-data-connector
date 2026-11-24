# Friction log: building the UDC MCP App with Skybridge

Notes taken while building this app (Skybridge **2.1.2**, `create-skybridge` 2.1.2,
skill pinned at `alpic-ai/skybridge@5cd3f8c`, Node 24.22, macOS), November 2026.
Each entry says what happened, its impact, and what would have helped.
**Observed** means it happened in this project; **documented** means it's from the
docs and not yet verified against a real host.

## Skill and onboarding

1. **The installed skill has no references (high).**
   `npx skills add alpic-ai/skybridge -s skybridge` installs `SKILL.md` but skips
   `references/`: in the repo it is a symlink to `../chatgpt-app-builder/references`,
   and the skills CLI refuses links that point outside the skill
   (`[SKILLS_SYMLINK_OUTSIDE_SKILL]`). All 17 `references/*.md` links in `SKILL.md` are
   dead, and `SKILL.md` is mostly a router to them, so an agent following the skill hits
   missing files on its first step. Observed.
   *Workaround*: copied `skills/chatgpt-app-builder/references` from the same commit.
   *Fix*: ship real files (or copy at publish time) instead of a cross-skill symlink.

2. **Two names for the skill.** The scaffolded `AGENTS.md` says "ALWAYS use the
   `chatgpt-app-builder` skill", the quickstart installs `skybridge`, and the repo
   ships both. An agent told to use one may not find it. Observed.

3. **A skill example doesn't type-check.** `references/prompt-llm.md` shows
   `sendMessage({ prompt: "…" })`; in 2.1.2 `useSendFollowUpMessage()` takes
   `(string | ContentBlock[], options?)`, as the API reference says. Observed (TS2353).

4. **Conflicting Node requirements.** The template says `engines.node >=24.0.0`, the
   published packages `>=22.23.1`, and the repo root `>=24.18.0`. Minor.

5. **Tool naming.** `architecture.md` recommends names like `search_flights`; every
   code example registers `search-flights`. Both work, but a single convention would
   help, since agents copy the examples. Minor.

6. **The Claude connector path differs between pages.** `test/tunnel.mdx`:
   *Customize → Connectors → Add custom connector*; the skill's `run-locally.md`:
   *claude.ai/settings/connectors → Add Custom Connector*. Minor.

## Building

7. **Unit-testing tool handlers is undocumented.** The docs cover DevTools (manual)
   and evals (live model, costs money, not unit tests). The fast path,
   `app.connect(InMemoryTransport)` with `@modelcontextprotocol/client`, only appears
   in Skybridge's own `app.test.ts`, and that client must be added as a direct
   devDependency (it is only transitive). A "Unit-test your tools" page with this
   pattern would make CI-friendly apps the default. Observed; used here.

8. **A view can't read its own tool's error.** `useToolInfo` exposes `output`
   (structuredContent) and `responseMetadata` (`_meta`), but not `content` or
   `isError`. A view whose tool failed only sees `output === undefined`. Workaround:
   the server repeats the error message in `_meta["udc/error"]`. A documented
   `error` / `isError` on `useToolInfo` would remove that. Observed.

9. **Two meanings of `isError` in `useCallTool`.** A tool result with `isError: true`
   is a *successful* call: `onSuccess` fires, the hook's `isError` stays `false`, and
   the flag is on `data.isError`. This is noted in the `SideEffects` comment, but the
   main example uses the hook's `isError` for "the action failed". Easy to get wrong
   in a human-in-the-loop UI where server-side rejections are the norm. Observed.

10. **`useViewState` default vs persisted state.** In DevTools, the first render of
    the review view crashed on `state.decisions[...]`, `decisions` being undefined
    although `defaultState` defines it. The docs say persisted state wins over the
    default; whatever DevTools supplied lacked the default's keys. The fix was
    defensive reads (`state?.decisions ?? {}`). Worth stating in the docs that the
    state can have any shape (older versions, other hosts). Observed in DevTools; the
    exact value DevTools supplied was not inspected.

11. **`view.component` isn't checked until types are generated.** `tsc` passed with
    `component: "mapping-review"` before the view file existed. The `.skybridge`
    types only appear after `dev`/`build`, so a typo can slip through a fresh-clone
    CI type check. Minor; observed.

## Running and observability

12. **`skybridge dev` is silent without a TTY.** Run from an agent shell or in the
    background, it prints nothing after the npm header: no MCP URL, no DevTools URL.
    The server was listening on :3000. `run-locally.md` tells agents to "output the
    local MCP server and devtools URL" from the dev server's output, which isn't
    possible here. A plain-text fallback (or `--plain`, like the Alpic CLI) would
    help. Observed.

13. **No conversation id outside ChatGPT.** MCP is served statelessly, so there is
    no MCP session. ChatGPT sends `openai/session` in `_meta`; nothing equivalent was
    found for other hosts. The client's identity is sent at `initialize`, a separate
    request, so tool calls can't be attributed to Claude vs ChatGPT except by user
    agent (the logs show `client: "node"` for the SDK client). This blocks
    per-conversation analysis and evals on real traffic. Observed (no session id,
    user-agent fallback); the per-host values are unverified.

14. **View calls look like model calls.** A `tools/call` made by the view
    (`useCallTool`) arrives exactly like one made by the model. For evaluation we
    want to know who acted, the human in the UI or the agent. Observed.

15. **DevTools logs 404s for OAuth discovery.** On a server without auth, DevTools
    requests `/.well-known/oauth-protected-resource[/mcp]`, and the browser console
    shows two 404 "Failed to load resource" errors on every load. They look like
    bugs. Minor; observed.

16. **Noise in test and build output.** Every vitest run prints "Sourcemap for
    `@skybridge/test/dist/matchers/index.js` points to missing source files". The
    scaffolded build warns that a chunk exceeds 500 kB (React + `@alpic-ai/ui`)
    before any app code is added. Minor; observed.

17. **The tunnel needs an Alpic account, and the docs don't say so.** `alpic whoami`
    reports "Not logged in. Run `alpic login` or set ALPIC_API_KEY"; `test/tunnel.mdx`
    doesn't mention logging in. Whether `--tunnel` works anonymously was not tested.

## Claude vs ChatGPT

Not yet tested against the real hosts (needs the tunnel and both accounts). Documented
differences that shaped the design:

- **ChatGPT** pushes an inline view's state to the model only at mount, so decisions
  made in an inline table may not reach the model. **Claude** may evict older view
  state. Design response: every decision is persisted in UDC, and the server
  instructions tell the agent to re-read the mapping before summarising or exporting.
- `openai/toolInvocation/*` status texts and `prefersBorder` are ChatGPT-only.
- Display modes: pip is ChatGPT-desktop-only; the review table only uses inline and
  fullscreen.

To fill in during tunnel testing:

- [ ] Does each host ask for confirmation on `propose_mapping` / `update_mapping`
      (`readOnlyHint: false`)? A confirmation per click in the table would be heavy.
- [ ] Does the model see `data-llm` / view state after decisions in inline mode?
- [ ] Do the native `<select>`s and fullscreen work in both hosts and on mobile?
- [ ] Values of `session_id` / `client` in the JSONL log for each host.

## What worked well

- `npm create skybridge@latest <dir> -- --yes --pm npm --skip-skills` scaffolds
  non-interactively; agent-friendly.
- `mcpMiddleware("tools/call")` with `getToolError(extra)` made the JSONL call log
  one small module (~160 lines with helpers), with no monkey-patching.
- `generateHelpers<AppType>()` typed `useCallTool("update_mapping")` arguments and
  results end to end; a renamed field breaks the view at compile time.
- DevTools runs the real view against the real server, with the state inspector
  and the Claude/ChatGPT preview shells. Driven headlessly (Playwright), it caught a
  view crash before any host did.
- The `setup` / `handler` split made dependency injection for tests straightforward.
