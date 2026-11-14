# AGENTS.md — dojo-plans

How coding agents change this repository; README.md says what it does.

## What this is

The `karate` origin's package plans for Dojo: one directory per package, holding its `plan.fnl` and
what the package carries. Plans are Fennel, loaded and built by `doj-plan-build` from Dojo's
`components/plan`; plan code never runs a shell, though a package's own scripts (`./configure`)
run through `b:run`. The tree forks the source project's plans at 10 April 2019 (`e831d067`) and
takes nothing later; that project's name appears nowhere in it.
Inherited and ported files keep their Apache 2.0 license and copyright; new work is MIT (`NOTICE`).
Never run a plan's bash: `tools/port` reads it statically, and downloaded files are data.
Scaffolded by smk proj from smkproj.toml; re-render with smk proj.

## Check

`make ci`: format, lint and types over every `plan.fnl`, `tools/builder` and the root's own files
(`smkproj.toml` excludes the rest and says why). Before a plan is committed it also passes
`tools/port/check.py`, and a claim that a translation is right needs a `tools/port/difftest` case.
Plans change through `tools/port`, never by editing a generated plan alone, so regenerating every
plan from its bash reproduces the tree. A plan that loads has not been shown to build: builds need
the `karate` base packages (`tools/builder`).

## Landing

Work in a tree (`trees add <name>`), commit on its `worktree/<name>` branch and open the pull
request with `smk pr create` and request its merge with `smk pr merge`, without asking. The host
is GitHub (`StripMallKarateCompany/dojo-plans`): buildq builds every push (`.buildq/pipeline.yml`
runs `make ci`), `main` requires its `buildq` status, and automerge's GitHub App lands a writer's
pull request once it passes (smk/automerge README "GitHub"). `.github/automerge.json` names the
merge commit as the one style. A buildq schedule builds `main` daily from `.buildq/daily.yml`, which smk leaves
alone, on the builder (`tools/builder/README.md`, "The daily build"). Pushed commits are never rebased, squashed or
amended. Live-state
changes outside a merge (a build on the builder host, a package upload to Builder) need explicit
authorization.

## Where the rest lives

Per-skill facts: `.agents/smk-context.md`, read by the skill that needs them. `CONTRIBUTING.md`
says how a plan and a commit are written, `tools/port/README.md` how plans are ported, `tools/builder/README.md`
how they build.
