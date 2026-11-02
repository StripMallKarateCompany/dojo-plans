# Contributing

A package is a directory named for it, holding its `plan.fnl` and anything the package carries: hooks
in `hooks/`, configuration templates in `config/`, defaults in `default.toml`, tests in `tests/`.
Plans are Fennel, loaded and checked by `doj-plan-build` from Dojo's `components/plan`; a plan
builds for Linux targets only.

- The origin is `karate` and the maintainer `Strip Mall Karate Company`.
- A plan's callbacks call the build's own operations (`b:run` with an argument list, `b:install`,
  `b:env` and the rest). A plan never runs a shell itself; a package's own scripts (`./configure`,
  `./bootstrap`) run through `b:run`.
- Every plan loads: `doj-plan-build show <dir>` prints its metadata.
- History is kept: no rebase, squash or amend of pushed commits, and pull requests land with merge
  commits. Commit subjects are imperative; bodies say why.
- The source project's name appears nowhere in the tree. Files that came from it keep their
  copyright and stay under the Apache License 2.0; new files are MIT (see `NOTICE`).
