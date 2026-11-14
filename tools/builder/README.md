# The plan builder

Plans build in a container on smk-1, Jamie's x86_64 Ubuntu box, so `x86_64-linux` packages build
natively on real hardware. The container is Ubuntu 26.04 with the tools a first build of the base
plans takes from its host (gcc, bison, gawk, m4, texinfo, Python), Rust to build `doj-plan-build`,
and swamp. Nothing is installed on smk-1 itself. smk-1 also runs the game fleet, the forge and
buildq, so the container is capped at 16 CPUs and 32 GB and every build runs under `nice -n 15`.

Run `tools/builder/builder` from a dojo-plans checkout on the Mac. `DOJO_BUILD_HOST` names another
box.

| Command                 | What it does                                                                                        |
| ----------------------- | --------------------------------------------------------------------------------------------------- |
| `image`                 | Builds the `dojo-builder` image on the host from `Containerfile` and `cc-wrapper`                   |
| `start`                 | Starts the container, with `/doj` in the `dojo-root` volume and `~/dojo-builder` at `/work`         |
| `sync [--force]`        | Unpacks this checkout's committed `HEAD` into `/work/plans`, keeping swamp's data and results       |
| `tools <dojo-checkout>` | Builds `doj-plan-build` and `doj` from that checkout's committed tree                               |
| `key`                   | Imports the karate origin's signing key pair from 1Password into `/doj/cache/keys`                  |
| `dojo <dojo-checkout>`  | Unpacks that checkout's committed `HEAD` into `/work/dojo`, for building Dojo's own component plans |
| `standins`              | Gives every base plan an empty `0.0.0` package, so a first build resolves its dependencies          |
| `gate`                  | Installs this checkout's `gate.py` and `state.py` on the host, for the daily build                  |
| `status`                | The plans' last builds counted by status, and the failures blocking the most plans                  |
| `wait`                  | Returns once nothing builds from `/work/plans`, riding out ssh failures for ten minutes             |
| `failures`              | One line per failed plan: its name, a tab, and the last error in its log                            |
| `check-wrapper`         | Links C and Rust programs with this checkout's `gcc/cc-wrapper.sh` and checks what it gives them    |
| `run <command>...`      | Runs a command in the container, from `/work/plans/swamp`, under `nice`                             |
| `shell`                 | A shell in the container                                                                            |
| `stop`, `remove`        | Stops the container; removes it and the `/doj` volume                                               |

From nothing: `image`, `start`, `sync`, `tools <dojo-checkout>`, `key`, `standins`. After a commit:
`sync`.

`status`, `wait` and `failures` pipe `state.py` into the container, which reads swamp's records and
processes there and changes nothing. Its parsing is tested from recorded swamp output (`bin/test`).

## Syncing beside a run

A running workflow reads `/work/plans` again at every wave, so syncing under it changes what the rest
of the run builds. `sync` therefore refuses while anything builds from `/work/plans`, naming it: a
`swamp workflow run` or `resume`, a `swamp behavior run`, a `doj-plan-build build`, or a workflow run
swamp never finished. `wait` for it, or `sync --force` to replace the tree anyway. A run swamp never
finished, with no process left behind it, makes `sync` refuse and `wait` exit 4: end it with
`swamp workflow cancel`, or continue it with `swamp workflow recover` and then `resume`.

`sync` sends one commit, so several branches that are waiting to merge build together only from a
commit that merges them. Keep a local `builder-head` branch that merges `origin/main` with every
pending branch, re-merge it when one changes, and sync only `builder-head`. Syncing a single branch
drops the others' changes from the tree.

## The daily build

A buildq schedule on dojo-plans (`@daily`, UTC) builds `main` from `.buildq/daily.yml` alone; a push
builds `.buildq/pipeline.yml`, which smk renders, and never this file, which smk leaves alone. Its one
step, `tools/builder/daily`, takes the `dojo-builder` queue, held only by the buildq agent of that name
on smk-1, which runs only this repository's `main`. The step checks that its build's `BUILDQ_SOURCE` is
`schedule`, and in any other build cancels itself. It sends its checkout's committed tree to the
builder, then builds each plan it names (`zlib` until DOJ-19 makes the step the daily bump).

The container belongs to the Docker daemon of its owner on the host, and whoever can run `docker` there
is root on smk-1, so the agent gets no Docker group and no shell. It reaches the builder through
`gate.py`: the agent's key is in the owner's `~/.ssh/authorized_keys` with a forced command, and the gate
runs one of three requests from `SSH_ORIGINAL_COMMAND`, refusing anything else:

| Request        | What the gate does                                                                       |
| -------------- | ---------------------------------------------------------------------------------------- |
| `sync`         | Unpacks the tar on stdin into `/work/daily` in the container, in place of what was there |
| `build <plan>` | `doj-plan-build build /work/daily/<plan> --target x86_64-linux`, under `nice`            |
| `running`      | `state.py running` in the container                                                      |

`sync` and `build` refuse (exit 3) while anything builds in the container, a person's run from
`/work/plans` included, so the daily build never syncs under a run or builds beside one; a run swamp
never finished, with no process behind it, does not hold it. `/work/plans` is never touched. The gate
and the `state.py` it asks are the copies `gate` installed in `~/.local/share/dojo-builder-gate`, outside
the container's mounts, so a build changes neither; reinstall after either changes. Packages the daily
build makes land in `/doj` beside a person's.

Setting it up changes live state, so each step needs Jamie's authorization:

1. `builder gate` from a checkout of `main`.
2. The agent: `[hosts.smk-1.agents.dojo-builder]` in smk/infrastructure's `inventory/hosts.toml`
   (`queues = ["dojo-builder"]`, `repositories = ["StripMallKarateCompany/dojo-plans"]`,
   `branches = ["main"]`, no credential), released with a signed `hosts-*` tag, then
   `make agent ARGS="smk-1 dojo-builder"`.
3. The agent's public key in the owner's `~/.ssh/authorized_keys` on smk-1, as
   `restrict,from="127.0.0.1,::1",command="python3 -I .local/share/dojo-builder-gate/gate.py" <key>`, and
   smk-1's host key pinned for `localhost` in the agent's `~/.ssh/known_hosts`.
4. The schedule: a `buildq_pipeline_schedule` in smk/infrastructure's `terraform/services/buildq/schedules.tf`
   for `StripMallKarateCompany/dojo-plans`, `cronline = "@daily"`, `branch = "main"`,
   `pipeline_file = ".buildq/daily.yml"`, applied by hand there.

## Checking gcc's wrapper

`check-wrapper` fills in `gcc/cc-wrapper.sh` as the gcc plan does, from the newest installed karate
gcc and that gcc's glibc and binutils, and links three programs with it in the container. C and Rust
against glibc must run, name that glibc's dynamic linker, and carry exactly `LD_RUN_PATH`'s entries
as their RUNPATH: rustc links with its bundled lld, which ignores `LD_RUN_PATH`. A static Rust program
against musl must run with no dynamic linker and no RUNPATH. It sends the working tree's wrapper, so a change is
checked before it is committed.

## What a build there is, and is not

- **The stand-ins are the first pass's host.** A stand-in is an empty package. The build uses the
  container's own tools, which are on PATH, and a real build of the package sorts after `0.0.0`
  and replaces it. Builds are not isolated from the container: the second, isolated pass waits on
  `doj-plan-build` gaining that mode.
- **The container's compiler links against karate's glibc.** A program linked against a karate
  glibc runs only with that glibc's dynamic linker, and the container's gcc names its own, so
  `gcc`, `cc`, `g++` and `c++` are wrappers (`cc-wrapper`) that add the karate glibc's dynamic
  linker to a link when the build has one. Once karate's gcc is built it comes first on PATH.
- **Artifacts are signed with the karate origin key.** `doj` is Dojo's own, built by `tools` with
  the image's Rust, so a builder with no karate packages has it. The key pair lives only in
  1Password, in "karate origin signing key" in the OMG SecOps vault, each key file base64-encoded
  in its own field (`public key`, `secret key`). `key` reads it with `op read`, so the 1Password
  app asks to approve, and imports it into the `/doj` volume; `remove` deletes it with the volume.
  It is in neither the image nor `~/dojo-builder` on the host.
- **swamp needs a swamp-club.com account.** Sign in once with `builder shell` and `swamp auth
login`. The credential is kept in `~/dojo-builder/home` on the host.
