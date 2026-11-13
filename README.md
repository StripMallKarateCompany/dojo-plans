# Dojo Plans

The plans that build [Dojo](https://github.com/StripMallKarateCompany/dojo)'s packages in the `karate`
origin: one directory per package, with the plan and whatever the package carries beside it (hooks,
configuration templates, `default.toml`, tests). Packages will be served from
`https://pkgs.karate.company/dojo/karate` (DOJ-29); the old Builder name, `bldr.karate.company`, is withdrawn
(Dojo's `docs/decisions.md`, 2026-11-13).

The tree starts from the source project's package plans as of 10 April 2019, the same point Dojo
itself forked from, with their history. Plans are written in Fennel, one `plan.fnl` per package (see
Dojo's `components/plan`), ported from the bash plans by `tools/port`. Plans build for Linux
only.

`base-plans.txt` lists the base toolchain in the order it is built. `.bldr.toml` says where each plan
lives; it keeps its inherited name until DOJ-17 removes `bldr` from Dojo and its plans.

[swamp](swamp/README.md) builds a plan and everything it depends on, in dependency order, with
`doj-plan-build`. [The builder](tools/builder/README.md) is where that runs: a container on
smk-1 that builds `x86_64-linux` packages natively.

## License

New work in Dojo Plans is MIT licensed: see [LICENSE](LICENSE). The plans and files inherited from
the source project, and the plans ported from them, stay under the Apache License 2.0 with Dojo's
changes to them: see [LICENSE-APACHE](LICENSE-APACHE) and [NOTICE](NOTICE).

Copyright (c) 2016 Chef Software Inc. and/or applicable contributors
Copyright (c) 2026 Strip Mall Karate Company
