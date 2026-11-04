# The plan.sh to plan.fnl port

The source project's plans (as of 10 April 2019) are bash; Dojo's are Fennel. These tools port them and
check the result. They go when the last `plan.sh` does.

## Running it

From the repository root, with `DPB` the `doj-plan-build` built from Dojo's `components/plan` (the
runtime the plans need is StripMallKarateCompany/dojo#6 and, for scaffoldings, #7 stacked on it; until
they merge, build #7's branch):

```sh
python3 -I tools/port/port.py <pkg>...            # writes <pkg>/plan.fnl; prints `ok` or what is left
python3 -I tools/port/check.py "$DPB" <pkg>...     # refuses a plan that is not ported, safe or loading
python3 -I tools/port/lints.py <plan.fnl>...       # rewrites a hand-written plan to pass fennel-ls
python3 -I tools/port/difftest/run.py <dojo-checkout> <builder-state> <builder-port>
python3 -I tools/port/buildtest/run.py <dojo-checkout> <builder-state> <builder-port> <stand-ins> <plan-dir>...
```

`difftest` needs the builder VM running (`support/vm/builder start` in a dojo checkout, with its own
`DOJO_BUILDER_STATE` and `DOJO_BUILDER_PORT`) and `doj-plan-build` built in it at
`~/plan-file-ops/target/debug/` (sync the runtime branch there and `cargo build -p dojo-plan`). It
runs each case in `difftest/cases.txt` as bash in one tree and as its Fennel translation in another;
the trees must match. Add a case for every new translation, and break the translation once to see
its case fail.

`buildtest` builds plans for real in the same VM, into `~/dojo-buildtest`, with Nix packages
standing in for the karate packages they need (its docstring has the stand-in syntax; a stand-in
named `test/<name>` is given to every plan, for tools a build host has). The scaffoldings, the
Go plans and the test apps in `buildtest/apps` were built this way, and their binaries run.

## What each file does

- `bashplan.py` reads a plan without running it: assignments, arrays, functions, `source` of another
  plan, and the parameter expansions plans use. A downloaded plan's bash never runs.
- `translate.py` turns each callback statement into b's operations. What it cannot say faithfully it
  keeps as bash in an `;; UNPORTED (...)` block.
- `port.py` writes the metadata and phases, renames to Dojo's names, and marks every problem in the
  plan's header so `check.py` holds it back. It formats each plan it writes as `smk format` does
  (fnlfmt, twice, since one pass leaves some plans unsettled) and runs `lints.py` on it, so
  regenerating a plan reproduces the committed one.
- `lints.py` rewrites a plan to pass fennel-ls's lints, from fennel-ls's report: method calls,
  nested `..`, a `var` never set, and the declarations the translator makes for every variable a bash
  function assigns. `port.py` runs it on each plan it writes; a definition it cannot remove without
  changing what the plan does becomes a problem in the header, for a person to read. `difftest` runs
  each case's Fennel through it, as `port.py` writes it.
- `check.py` refuses: an UNPORTED block, a shell given code (`sh -c`), the source project's name, a b
  operation on a path outside `/doj`, a builder function or shell builtin run as a program, and a plan
  `doj-plan-build show` does not load.
- `handported.txt`: statements a person ported, keyed by their bash. The translator uses an entry
  before its own reading, wherever the statement appears, so one entry serves a plan and every plan
  that sources it.
- `handwritten.txt`: plans written by hand whole, which `port.py` leaves alone.

## Workflow

1. Port the package. If it prints `ok` and `check.py` passes, `git add <pkg>/plan.fnl` and
   `git rm <pkg>/plan.sh` (and any `x86_64-linux-kernel2/plan.sh` and sourced data `.sh`), unless
   another plan still sources this one (the base stays until its variants are ported).
2. Otherwise read each UNPORTED block. A mechanical form goes into `translate.py` with a difftest
   case; a one-off goes into `handported.txt`.
3. After any translator change, regenerate every committed plan from its original bash in a scratch
   worktree (`git show e831d067:<pkg>/plan.sh`) and compare with what is committed. Each difference
   is a fix to adopt or a regression to fix. This found bugs reading never did.

## Decisions (Jamie, 2026-10-26)

- Fork at 10 April 2019 (`e831d067`), history kept; pure Fennel (no shell in plan code); Windows
  plans dropped.
- The old studio linked a dependency's tool into `/usr/bin` for builds: ported as
  `use-dependency-path`, which points the build's scripts at the dependency instead.
- `do_clean` overrides are dropped: a build always starts from a fresh source directory.
- Unverified sources are pinned to a checksummed archive current at the fork date.
- concourse-fly is dropped. jdk8, jdk9, jre8 and jre9 (Oracle's, behind a sign-in now and
  limited in redistribution) are dropped; plans that used jdk8 or jre8 use corretto8, the same Java.
- Scaffoldings are their own stage: their `plan.fnl` packages the bash library faithfully, but Dojo's
  scaffoldings are Fennel modules, still to write.

## Semantics the translation rests on

- The source project's builder ran callbacks under `set -e` (from memory of plan-build, about 80%
  sure): a failing command stopped the build, so `$?` after a command is 0 and `|| return` is the
  command alone. `|| true` is `b:run` with `{:check false}`.
- Each callback ran in the source directory; `pushd`/`cd` there are `:cwd`. b resolves a relative
  path for writes inside the prefix, so every path the translator passes to b is made absolute, and
  variables that may hold relative paths (a relative glob's names, a `find`'s lines) are anchored.
- Approximations: `-d`, `-x` and `-s` tests are "exists"; `printf`/`cat` into a file may gain a
  trailing newline.

## Choices made in the port (Claude's judgment, open to Jamie)

- Builds may write anywhere in `b.cache`: the source project's plans move downloads, unpack beside
  the source and configure in `../<name>-build` there (StripMallKarateCompany/dojo#6).
- The source project's stage1 studio does not exist in Dojo; branches for it are notes.
- A tool link the source never names (linux's `/bin/pwd`) is a note, not a `use-dependency-path`.
- bash-static's own `do_begin` replaced bash's, which read the patch list: it applied no patches,
  and neither does the port (`UNSET_ARRAYS` in `port.py`).
- Pins, each the newest at the fork date unless the plan named a version: rust-nightly and
  cargo-nightly from the 2019-04-09 nightly's manifest; awscli 1.16.140 from PyPI; boringssl branch
  3538's head from the GitHub mirror; img's v0.5.4 tag; prometheus-cpp v0.6.0 and its submodules at
  the recorded commits; netcat-openbsd's Debian 1.105-7 patches from snapshot.debian.org.

## Hand entries match by statement

An entry in `handported.txt` replaces its statement wherever it appears, in any plan. An entry
holding one plan's values (rust's target URL, linux's dependency list, glibc's tzdata source) must
either be unique to that plan or refuse another (glibc's does). Check with `git grep` on a value
from the entry after porting.

## Scaffoldings

A scaffolding is a package shipping `lib/scaffolding.fnl`, a Fennel module: phases, helpers plans
call through `b.scaffolding`, and a `metadata` function that reads the app's files and adds
dependencies, the service and exports to the plan (StripMallKarateCompany/dojo#7). A plan gives it
settings with `:scaffolding {:package <ident> :settings {...}}`. scaffolding-base, scaffolding-go,
scaffolding-node and scaffolding-ruby are ported; chef, inspec, gradle and go17 were dropped
(Jamie, 2026-10-26).

- scaffolding-go puts the source at its import path in a GOPATH of the build's own and passes the
  build's flags to cgo. The Go plans' sources are their tags' archives; where a build asked git for
  its version, the plan passes the tag's values (ldflags or make variables). glide v0.13.2, gox
  v1.0.0 and go-bindata's last 2018 commit are pinned where the plans fetched them at HEAD; Makefiles
  that run `/bin/bash` get the bash dependency as `SHELL`.
- scaffolding-node matches `engines.node` against the Node packages this repository builds (there
  is no Builder to ask); scaffolding-ruby reads Gemfile.lock in Fennel and needs one present.
- A user and group with no service to run are left out of `svc` (chrony, systemd).

## What is left

Nothing: every plan is Fennel. geoip, whose GeoLite download no longer exists, and openssl-fips,
whose FIPS canister OpenSSL 3 replaced with a provider built from OpenSSL itself, were dropped
(Jamie, 2026-10-26).

## Sources that no longer answer

Of 548 committed source URLs, 71 failed a one-byte fetch on 2026-10-26 (ftp.gnupg.org's FTP,
moved paths on cache.ruby-lang.org, php.net, storage.googleapis.com and others). Those packages, and
every plan in `base-plans.txt`, take their latest upstream release instead (Jamie, 2026-10-26); each
bumped plan says so in its second line and is in `handwritten.txt`, since its bash no longer
describes it. A bumped plan loads; whether it builds is shown only by building it.
