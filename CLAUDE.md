Be concise and action-oriented.

Default to doing the work directly instead of over-explaining.

Do not build, package, or release anything unless I explicitly ask.

## CRITICAL MODE CONTROL

- Default to PLANNING MODE unless I explicitly say: START BUILD PHASE X
- In PLANNING MODE:
  - Do NOT write code
  - Do NOT create files
  - Focus only on architecture, modules, and flow

- In BUILD MODE:
  - Only execute the requested phase
  - Do NOT jump ahead to future phases
  - Do NOT redesign architecture unless I explicitly ask

## TOKEN CONTROL RULES

- Keep responses compact and structured
- Do NOT reprint full files unless necessary
- Only show:
  - changed sections
  - new files
  - relevant snippets
- Summarize large unchanged code blocks
- Avoid repeating previous outputs

## BUILD DISCIPLINE

- Follow the defined phase strictly
- Do not add extra features unless asked
- Do not over-engineer
- Prefer simple, maintainable solutions

## REPO BOUNDARY RULES

- Treat this repository as the only source of truth unless I explicitly tell you to inspect another repo.
- Do NOT search sibling projects in `~/Projects` for patterns, scripts, packaging logic, or build workflows.
- Do NOT infer how this repo should build Windows artifacts from other Cove repos.
- Only use files that exist inside the current repository to determine build, packaging, release, and signing steps.
- If the current repo does not contain enough information to build a Windows artifact, say exactly what is missing instead of borrowing another repo’s process.
- Do not tell me to “build it on Windows” unless the current repo explicitly requires that.
- For build/release tasks, verify commands and packaging paths from this repo’s files first, then report the exact source file used.
- If I mention another project by name, ask before reusing its workflow here.
- Never run `find ~/Projects` or inspect other Cove repositories for build guidance unless I explicitly request cross-project comparison.

## WINDOWS ARTIFACT RULE

- When I ask for `.exe`, `Portable.exe`, or `Setup.exe`, first check whether this repo itself already has packaging scripts, specs, or release conventions.
- If yes, use only those repo-local instructions.
- If no, stop and tell me the current repo lacks a defined Windows packaging path.
- Do not search other repositories to fill in missing packaging steps.

## OUTPUT CONTROL

When implementing:
- Prefer minimal diffs over full rewrites
- Group related changes
- Clearly label files touched
- Avoid unnecessary verbosity

## FAILURE HANDLING

If something is unclear or missing:
- State exactly what is missing
- Do NOT guess
- Do NOT fabricate structure or files
