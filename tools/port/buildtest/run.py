"""Builds plans for real in the builder VM, with stand-ins for the karate packages they need.

    python3 tools/port/buildtest/run.py <dojo-checkout> <builder-state> <builder-port> <stand-ins> <plan-dir>...

<stand-ins> names the dependencies to stand in for, `ident=nix-installable` separated by commas
(`karate/git=github:NixOS/nixpkgs/nixos-24.05#git`), or `ident=nixos-<release>:<expression>`, an
expression in the scope of that release's package set, from before flakes (`karate/go=nixos-19.09:go_1_12`). Each becomes a package whose PATH, compiler
flags and pkg-config path name the installable's bin, include and lib directories (a symlinkJoin
gives a library with several outputs one). The plans build in the order given, for aarch64-linux (a plan that
lists only x86_64-linux is built as if it listed aarch64-linux too), into ~/dojo-buildtest in the
VM, which keeps what was built for the next run; each later plan finds the earlier ones. Needs
doj-plan-build built at ~/plan-file-ops/target/debug/ in the VM, as difftest does.
Prints each plan's result and the end of a failed build's log; exits nonzero if any failed.
"""

import os
import shlex
import shutil
import subprocess
import sys
import tempfile

VM_SCRIPT = r"""
set -uo pipefail
work=$1; tool=$2; standins=$3; shift 3
root=$HOME/dojo-buildtest
mkdir -p "$root/pkgs" "$root/keys" "$root/out"
: > "$root/keys/karate-20200101000000.sig.key"
: > "$root/keys/test-20200101000000.sig.key"
export NIX_CONFIG="extra-experimental-features = nix-command flakes"
# The stand-ins: packages whose PATH is a Nix installable's bin directory.
IFS=, read -ra pairs <<< "$standins"
for pair in "${pairs[@]}"; do
  [[ -n "$pair" ]] || continue
  ident=${pair%%=*}; installable=${pair#*=}
  if [[ "$installable" =~ ^(nixos-[0-9]+\.[0-9]+):(.+)$ ]]; then
    # Before flakes: an attribute of that release's package set.
    out=$(nix build --impure --no-link --print-out-paths --expr \
      "with (import (fetchTarball \"https://github.com/NixOS/nixpkgs/archive/${BASH_REMATCH[1]}.tar.gz\") {}); (${BASH_REMATCH[2]})" \
      2>/dev/null | grep -v -E -- "-(man|dev|doc|info|debug)$" | head -1)
  else
    out=$(nix build --impure --no-link --print-out-paths "$installable" 2>/dev/null | grep -v -E -- "-(man|dev|doc|info|debug)$" | head -1)
  fi
  [[ -n "$out" ]] || { echo "stand-in $ident: $installable did not build"; exit 1; }
  dir="$root/pkgs/$ident/0.0.0/20200101000000"
  mkdir -p "$dir"
  # The installable's top-level entries, in the package; its PATH and flags
  # name directories inside the package.
  for entry in "$out"/*; do
    ln -sfn "$entry" "$dir/$(basename "$entry")"
  done
  [[ -d "$out/bin" ]] && echo "$dir/bin" > "$dir/PATH"
  if [[ -d "$out/include" ]]; then
    echo "-I$dir/include" > "$dir/CFLAGS"; echo "-I$dir/include" > "$dir/CPPFLAGS"; echo "-I$dir/include" > "$dir/CXXFLAGS"
  fi
  if [[ -d "$out/lib" ]]; then
    echo "-L$dir/lib" > "$dir/LDFLAGS"; echo "$dir/lib" > "$dir/LD_RUN_PATH"
    [[ -d "$out/lib/pkgconfig" ]] && echo "$dir/lib/pkgconfig" > "$dir/PKG_CONFIG_PATH"
  fi
  echo "$ident/0.0.0/20200101000000" > "$dir/IDENT"
done
# doj: `pkg path` finds the newest installed package; anything else is signing.
cat > "$work/doj" <<'STUB'
#!/usr/bin/env bash
if [[ "$1" == pkg && "$2" == path ]]; then
  dir=$(ls -d "$DOJ_ROOT_PATH/pkgs/$3" 2>/dev/null | grep -v -E -- "-(man|dev|doc|info|debug)$" | head -1)
  [[ -n "$dir" ]] || exit 1
  while [[ ! -f "$dir/IDENT" ]]; do
    next=$(ls -d "$dir"/*/ 2>/dev/null | sort | tail -1)
    [[ -n "$next" ]] || exit 1
    dir=${next%/}
  done
  echo "$dir"
  exit 0
fi
{ echo "signed by $4"; cat "$5"; } > "$6"
STUB
chmod +x "$work/doj"
status=0
for plan in "$@"; do
  name=$(basename "$plan")
  sed -i 's/:targets \["x86_64-linux"\]/:targets ["x86_64-linux" "aarch64-linux"]/' "$work/plans/$plan/plan.fnl"
  # Tools the build host would have: stand-ins named test/<name>, given to every
  # plan as build dependencies (binutils' strip; Python for node-gyp on aarch64).
  extra=""
  for pair in "${pairs[@]}"; do
    [[ "$pair" == test/* ]] && extra="$extra \"${pair%%=*}\""
  done
  if [[ -n "$extra" ]]; then
    plan_file="$work/plans/$plan/plan.fnl"
    if grep -q '^ :build_deps \[' "$plan_file"; then
      sed -i "s|^ :build_deps \[|  :build_deps [$extra |" "$plan_file"
    else
      sed -i "s|^ :targets |  :build_deps [$extra]\n :targets |" "$plan_file"
    fi
  fi
  log="$work/$name.log"
  if DOJ_ROOT_PATH="$root" DOJ_CACHE_KEY_PATH="$root/keys" DOJ_OUTPUT_PATH="$root/out" DOJ_BIN="$work/doj" \
       "$tool" build "$work/plans/$plan" --target aarch64-linux > "$log" 2>&1; then
    echo "$name: built $(grep -o 'Installed [^ ]*' "$log" | tail -1)"
  else
    echo "$name: failed"; tail -25 "$log" | sed 's/^/    /'; status=1
    cp "$log" "$root/last-failed.log"
  fi
done
exit $status
"""


def main(argv):
    if len(argv) < 5:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    checkout, state, port, standins, *plans = argv
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with tempfile.TemporaryDirectory() as tmp:
        for plan in plans:
            shutil.copytree(os.path.join(repo, plan), os.path.join(tmp, "plans", plan),
                            ignore=shutil.ignore_patterns("plan.sh"))
        with open(os.path.join(tmp, "run.sh"), "w", encoding="utf-8") as f:
            f.write(VM_SCRIPT)
        archive = shutil.make_archive(os.path.join(tmp, "buildtest"), "tar", tmp, ".")
        remote = ("set -e; d=$(mktemp -d); tar --warning=no-timestamp -xf - -C \"$d\"; "
                  "bash \"$d/run.sh\" \"$d\" \"$HOME/plan-file-ops/target/debug/doj-plan-build\" "
                  + shlex.join([standins] + plans) + "; s=$?; rm -rf \"$d\"; exit $s")
        env = dict(os.environ, DOJO_BUILDER_STATE=state, DOJO_BUILDER_PORT=port)
        with open(archive, "rb") as f:
            ran = subprocess.run([os.path.join(checkout, "support/vm/builder"), "ssh", remote], stdin=f,
                                 env=env, cwd=checkout, capture_output=True, text=True, check=False)
        sys.stdout.write(ran.stdout)
        sys.stderr.write("".join(line for line in ran.stderr.splitlines(True) if "Pseudo-terminal" not in line))
        return 0 if ran.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
