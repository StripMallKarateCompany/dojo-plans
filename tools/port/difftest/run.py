"""Checks the translator by running each case both ways and comparing what they leave.

    python3 tools/port/difftest/run.py <dojo-checkout> <builder-state> <builder-port>

For each case in cases.txt, bash runs the body in one tree and the plan
runtime runs its Fennel translation in another, in the builder VM (the
runtime builds only for its host's target). The prefixes and the source
directories must match: names, types, modes, link targets and contents.
Prints one line per case and exits nonzero on any difference.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import bashplan  # noqa: E402
import lints  # noqa: E402
import translate  # noqa: E402


def cases(path):
    found = []
    current = None
    section = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("== "):
                current = {"name": line[3:].strip(), "setup": [], "body": []}
                found.append(current)
                section = None
            elif line.startswith("-- ") and current is not None:
                section = line[3:].strip()
            elif current is not None and section in ("setup", "body"):
                current[section].append(line)
            elif line.strip() and not line.startswith("#"):
                raise ValueError(f"cases.txt: stray line {line!r}")
    for case in found:
        case["setup"] = "".join(case["setup"]).strip() + "\n"
        case["body"] = "".join(case["body"]).strip() + "\n"
    return found


def plan_for(case):
    plan = bashplan.Plan()
    plan.scalars.update({"pkg_name": "difftest", "pkg_version": "1.0"})
    forms, unported = translate.translate_function("do_build", case["body"], plan, "difftest")
    if unported:
        return None, "; ".join(why for why, _ in unported)
    body = translate.indent(forms, 10) if forms else "          nil"
    text = ('{:name "difftest" :origin "karate" :version "1.0" :targets ["aarch64-linux"]\n'
            f" :build (fn [b]\n{body})\n :install (fn [b] nil)}}\n")
    # The case runs the Fennel port.py writes: the translation after its lint pass.
    text, left = lints.clean(text.encode())
    if left:
        return None, "; ".join(f"line {line}: {message}" for line, message in left)
    return text.decode(), None


VM_SCRIPT = r"""
set -uo pipefail
root=$1; tool=$2
listing() { (cd "$1" && find . -mindepth 1 ! -name plan.fnl ! -name setup.sh ! -name body.sh \
  -printf '%P %y %m %l\n' | sort; find . -type f ! -name plan.fnl ! -name setup.sh ! -name body.sh \
  -printf '%P\n' | sort | while read -r f; do printf '%s %s\n' "$f" "$(sha256sum < "$f" | cut -c1-16)"; done); }
prefix_listing() { (cd "$1" && find . -mindepth 1 ! -regex '\./[A-Z_]+' -printf '%P %y %m %l\n' | sort;
  find . -type f ! -regex '\./[A-Z_]+' -printf '%P\n' | sort | while read -r f; do printf '%s %s\n' "$f" "$(sha256sum < "$f" | cut -c1-16)"; done); }
status=0
for case in "$root"/cases/*/; do
  name=$(basename "$case")
  work=$(mktemp -d)
  mkdir -p "$work/a/src" "$work/a/prefix" "$work/b/plan" "$work/b/root" "$work/b/keys" "$work/b/out"
  cp "$case/plan.fnl" "$work/b/plan/"
  ( cd "$work/a/src" && pkg_prefix="$work/a/prefix" pkg_name=difftest body="$case/body.sh" bash -c \
      'set -e; build_line() { echo "$*"; }; source "$1"; f() { source "$body"; }; f' _ "$case/setup.sh" ) > "$work/a.log" 2>&1
  a=$?
  ( cd "$work/b/plan" && pkg_prefix=/nonexistent bash -c 'set -e; source "$1"' _ "$case/setup.sh" ) > /dev/null 2>&1
  : > "$work/b/keys/karate-20200101000000.sig.key"
  printf '#!/bin/sh\n{ echo "signed by $4"; cat "$5"; } > "$6"\n' > "$work/b/doj"; chmod +x "$work/b/doj"
  DOJ_ROOT_PATH="$work/b/root" DOJ_CACHE_KEY_PATH="$work/b/keys" DOJ_OUTPUT_PATH="$work/b/out" \
    DOJ_BIN="$work/b/doj" "$tool" build "$work/b/plan" --target aarch64-linux > "$work/b.log" 2>&1
  b=$?
  prefix=$(ls -d "$work"/b/root/pkgs/karate/difftest/1.0/* 2>/dev/null | head -1)
  if [[ $a -ne 0 || $b -ne 0 || -z "$prefix" ]]; then
    echo "$name: bash exit $a, fennel exit $b"; { tail -2 "$work/a.log"; grep -E 'failed|error' "$work/b.log" | tail -2; } | sed 's/^/    /'; status=1
  elif ! { diff <(listing "$work/a/src") <(listing "$work/b/plan") > "$work/src.diff";
           s1=$?; diff <(prefix_listing "$work/a/prefix") <(prefix_listing "$prefix") > "$work/prefix.diff";
           [[ $s1 -eq 0 && $? -eq 0 ]]; }; then
    echo "$name: differs"; cat "$work/src.diff" "$work/prefix.diff" | head -12 | sed 's/^/    /'; status=1
  else
    echo "$name: same"
  fi
  rm -rf "$work"
done
exit $status
"""


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    checkout, state, port = argv
    status = 0
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases(os.path.join(HERE, "cases.txt")):
            plan, why = plan_for(case)
            if plan is None:
                print(f"{case['name']}: not translated: {why}")
                status = 1
                continue
            d = os.path.join(tmp, "cases", case["name"])
            os.makedirs(d)
            for name, text in (("plan.fnl", plan), ("setup.sh", case["setup"]), ("body.sh", case["body"])):
                with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                    f.write(text)
        with open(os.path.join(tmp, "run.sh"), "w", encoding="utf-8") as f:
            f.write(VM_SCRIPT)
        archive = shutil.make_archive(os.path.join(tmp, "difftest"), "tar", tmp, ".")
        # Perl with local::lib, which the plans' Perl cases run.
        perl = ("export NIX_CONFIG='extra-experimental-features = nix-command flakes'; "
                "p=$(nix build --no-link --print-out-paths github:NixOS/nixpkgs/nixos-24.05#perl538 "
                "github:NixOS/nixpkgs/nixos-24.05#perl538Packages.locallib 2>/dev/null); "
                "export PATH=\"$(echo \"$p\" | grep -v local-lib | head -1)/bin:$PATH\" "
                "PERL5LIB=\"$(ls -d \"$(echo \"$p\" | grep local-lib | head -1)\"/lib/perl5/site_perl/5*)\"; ")
        remote = (perl + "set -e; d=$(mktemp -d); tar --warning=no-timestamp -xf - -C \"$d\"; "
                  "bash \"$d/run.sh\" \"$d\" \"$HOME/plan-file-ops/target/debug/doj-plan-build\"; "
                  "s=$?; rm -rf \"$d\"; exit $s")
        env = dict(os.environ, DOJO_BUILDER_STATE=state, DOJO_BUILDER_PORT=port)
        with open(archive, "rb") as f:
            ran = subprocess.run([os.path.join(checkout, "support/vm/builder"), "ssh", remote], stdin=f,
                                 env=env, cwd=checkout, capture_output=True, text=True, check=False)
        sys.stdout.write(ran.stdout)
        sys.stderr.write("".join(line for line in ran.stderr.splitlines(True) if "Pseudo-terminal" not in line))
        status = status or ran.returncode
    return 1 if status else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
