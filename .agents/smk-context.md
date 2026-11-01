# Project context

Per-skill facts for this repository. A skill reads the section named for it; `AGENTS.md` holds what
every change needs.

## Tools-engineer

- `tools/port` ports the source project's bash plans to Fennel and checks the result:
  [tools/port/README.md](../tools/port/README.md) has the commands, the workflow, the translation
  semantics and the decisions the port rests on. The tools leave with the last `plan.sh`.
- `smk format` and `smk lint` cover every `plan.fnl` (fnlfmt, and fennel-ls with every lint it
  ships, set in `flsproject.fnl`), `tools/builder` and the root's own files. The rest of each plan
  directory is the package's inherited data and `tools/port` is untyped, so `smkproj.toml`'s
  `Format.Exclude` leaves them out and says why beside each entry. `tools/port/port.py` runs fnlfmt
  twice over each plan it writes and rewrites it with `tools/port/lints.py` to pass fennel-ls, so a
  regenerated plan matches the committed one byte for byte.
- `tools/builder` runs plans' builds in a container on smk-1, natively for `x86_64-linux`:
  [tools/builder/README.md](../tools/builder/README.md) has its commands and first-build order.
  A build there changes live state and needs explicit authorization.
