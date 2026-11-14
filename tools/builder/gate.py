"""The plan builder's gate: the few things a scheduled dojo-plans build may ask of the builder.

    ssh <owner>@localhost sync < tree.tar    # SSH_ORIGINAL_COMMAND="sync"
    ssh <owner>@localhost build <plan>
    ssh <owner>@localhost running

The builder container belongs to the Docker daemon of the user who runs it on smk-1, and whoever can
run `docker` there is root on the box. So the daily build's agent gets no shell as that user and no
Docker group: its key is in the owner's authorized_keys with `restrict` and a forced command that runs
this file, installed by `builder gate` outside the container's mounts, and sshd hands the command the
agent asked for in SSH_ORIGINAL_COMMAND. Nothing else is run for it:

- sync: unpacks a plans tree (a tar on stdin, at most MAX_TREE_BYTES) into /work/daily in the
  container, in place of what was there. /work/plans, where a person's runs build, is not touched.
- build <plan>: `doj-plan-build build` of /work/daily/<plan> for x86_64-linux, under `nice`.
- running: state.py's `running` in the container.

sync and build refuse while anything builds in the container (state.py's exit 3), so the daily build
never changes a tree under a run or builds beside one. The tree's content is data to this file: it is
unpacked and built inside the container, as `builder sync` and a person's builds do.

Exit: the command's own status; 2 for a request this file does not run; 3 while something builds.
"""

import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, BinaryIO

CONTAINER = "dojo-builder"
DAILY = "/work/daily"
TARGET = "x86_64-linux"
# The committed tree is about 5 MB; a stream past this is not a plans tree.
MAX_TREE_BYTES = 256 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
EXIT_USAGE = 2
# state.py's `running` exit status when something builds, which this file passes on.
EXIT_RUNNING = 3
# A plan is a directory of the repository's root: its name, as the tree spells it (R, omniORB, 7zip).
PLAN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
STATE = Path(__file__).resolve().with_name("state.py")
# Replaces /work/daily with the tree on stdin, unpacked beside it first so a broken stream leaves the
# last tree whole. It runs in the container, as the builder user.
UNPACK = f"""set -e
rm -rf {DAILY}.new
mkdir {DAILY}.new
tar -xmf - --no-same-owner -C {DAILY}.new
rm -rf {DAILY}
mv {DAILY}.new {DAILY}
"""


@dataclass(frozen=True)
class Request:
    command: str
    plan: str | None = None


class Refused(Exception):
    """A request this file does not run, with why."""


def parse(original: str) -> Request:
    """The request in SSH_ORIGINAL_COMMAND, split on whitespace: a shell never reads it."""
    words = original.split()
    match words:
        case ["sync"] | ["running"]:
            return Request(words[0])
        case ["build", plan]:
            if not PLAN_NAME.fullmatch(plan):
                raise Refused(f"not a plan name: {plan!r}")
            return Request("build", plan)
        case _:
            raise Refused(
                f"not a request the gate runs: {original!r}; it runs sync, build <plan> and running"
            )


def docker_exec(
    *args: str, stdin: bool = False, workdir: str | None = None
) -> list[str]:
    command = ["docker", "exec"]
    if stdin:
        command.append("-i")
    if workdir is not None:
        command += ["-w", workdir]
    return [*command, CONTAINER, *args]


def state(command: str) -> subprocess.CompletedProcess[str]:
    """state.py's command in the container, from swamp's repository, its output kept for the caller."""
    with STATE.open("rb") as script:
        return subprocess.run(
            docker_exec(
                "python3", "-I", "-", command, stdin=True, workdir="/work/plans/swamp"
            ),
            stdin=script,
            capture_output=True,
            text=True,
            check=False,
        )


def refuse_while_building() -> int:
    """0 when nothing builds; otherwise what builds, on stderr, and the status to exit with."""
    found = state("running")
    if found.returncode == EXIT_RUNNING:
        sys.stderr.write(found.stdout)
        print(
            "gate: something builds in the container; not starting beside it",
            file=sys.stderr,
        )
        return EXIT_RUNNING
    if found.returncode not in (0, 4):
        sys.stderr.write(found.stdout + found.stderr)
        print(
            f"gate: could not tell whether anything builds (state.py exit {found.returncode})",
            file=sys.stderr,
        )
        return found.returncode
    return 0


def copy_limited(source: BinaryIO, sink: IO[bytes], limit: int) -> bool:
    """Copies source to sink; False, having stopped, once more than limit bytes arrive."""
    sent = 0
    while chunk := source.read(CHUNK_BYTES):
        sent += len(chunk)
        if sent > limit:
            return False
        sink.write(chunk)
    return True


def sync(source: BinaryIO) -> int:
    with subprocess.Popen(
        docker_exec("sh", "-c", UNPACK, stdin=True), stdin=subprocess.PIPE
    ) as unpack:
        assert unpack.stdin is not None  # stdin=PIPE gives one
        try:
            whole = copy_limited(source, unpack.stdin, MAX_TREE_BYTES)
        except BrokenPipeError:
            whole = True  # tar stopped reading; its exit says why
        if not whole:
            unpack.kill()
            unpack.wait()
            print(
                f"gate: the tree is over {MAX_TREE_BYTES} bytes; /work/daily is unchanged",
                file=sys.stderr,
            )
            return 1
        unpack.stdin.close()
        return unpack.wait()


def build(plan: str) -> int:
    directory = f"{DAILY}/{plan}"
    if (
        subprocess.run(
            docker_exec("test", "-f", f"{directory}/plan.fnl"), check=False
        ).returncode
        != 0
    ):
        print(
            f"gate: {directory} holds no plan.fnl; sync a tree that has it",
            file=sys.stderr,
        )
        return 1
    return subprocess.run(
        docker_exec(
            "nice",
            "-n",
            "15",
            "doj-plan-build",
            "build",
            directory,
            "--target",
            TARGET,
            workdir=DAILY,
        ),
        check=False,
    ).returncode


def run(request: Request, source: BinaryIO) -> int:
    if request.command == "running":
        found = state("running")
        sys.stdout.write(found.stdout)
        sys.stderr.write(found.stderr)
        return found.returncode
    if (status := refuse_while_building()) != 0:
        return status
    if request.command == "sync":
        return sync(source)
    assert request.plan is not None  # parse gives build its plan
    return build(request.plan)


def main(environ: Mapping[str, str], argv: Sequence[str], source: BinaryIO) -> int:
    if len(argv) != 0:
        print(
            "gate: takes its request from SSH_ORIGINAL_COMMAND, not arguments",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        request = parse(environ.get("SSH_ORIGINAL_COMMAND", ""))
    except Refused as refused:
        print(f"gate: {refused}", file=sys.stderr)
        return EXIT_USAGE
    return run(request, source)


if __name__ == "__main__":
    sys.exit(main(os.environ, sys.argv[1:], sys.stdin.buffer))
