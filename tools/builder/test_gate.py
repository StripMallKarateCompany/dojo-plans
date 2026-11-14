"""Tests for gate.py and the daily build's step (daily), run as sshd and buildq run them.

    python3 -m unittest discover -s tools/builder

Each test puts a fake `docker`, `ssh` or `buildq-agent` first on PATH. The fake records each call's
arguments, and what it read on stdin, as one JSON line in calls.jsonl, and answers as its FAKE_
variables say.
"""

import io
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any

import gate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FAKE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    data = b"" if sys.stdin.isatty() else sys.stdin.buffer.read()
    with open(os.environ["FAKE_CALLS"], "a", encoding="utf-8") as calls:
        calls.write(json.dumps({"program": os.path.basename(sys.argv[0]), "args": args, "stdin": len(data)}) + "\\n")
    if "python3" in args:
        print("process 42 doj-plan-build build /work/plans/gcc")
        sys.exit(int(os.environ.get("FAKE_RUNNING", "0")))
    if "test" in args:
        sys.exit(int(os.environ.get("FAKE_PLAN", "0")))
    if "doj-plan-build" in args:
        sys.exit(int(os.environ.get("FAKE_BUILD", "0")))
    if "build" in args:
        sys.exit(int(os.environ.get("FAKE_BUILD", "0")))
    sys.exit(0)
    """
)


class Fakes:
    def __init__(self, directory: Path) -> None:
        self.bin = directory / "bin"
        self.bin.mkdir()
        self.calls = directory / "calls.jsonl"
        for name in ("docker", "ssh", "buildq-agent"):
            path = self.bin / name
            path.write_text(FAKE, encoding="utf-8")
            path.chmod(0o755)

    def env(self, **values: str) -> dict[str, str]:
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("BUILDQ", "SSH_", "FAKE_", "DOJO_"))
        }
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        env["FAKE_CALLS"] = str(self.calls)
        env.update(values)
        return env

    def recorded(self) -> list[dict[str, Any]]:
        if not self.calls.exists():
            return []
        return [
            json.loads(line)
            for line in self.calls.read_text(encoding="utf-8").splitlines()
        ]


class Parse(unittest.TestCase):
    def test_reads_the_three_requests(self) -> None:
        self.assertEqual(gate.parse("sync"), gate.Request("sync"))
        self.assertEqual(gate.parse("running"), gate.Request("running"))
        self.assertEqual(gate.parse("build zlib"), gate.Request("build", "zlib"))

    def test_takes_plan_names_as_the_tree_spells_them(self) -> None:
        for plan in ("R", "omniORB", "7zip", "libstdc++", "python2.7", "bash-static"):
            self.assertEqual(gate.parse(f"build {plan}").plan, plan)

    def test_refuses_anything_else(self) -> None:
        for original in (
            "",
            "sh",
            "sync now",
            "build",
            "build a b",
            "build ../etc",
            "build .hidden",
            "build zlib;id",
            "build $(id)",
            "docker exec dojo-builder bash",
        ):
            with self.subTest(original=original), self.assertRaises(gate.Refused):
                gate.parse(original)


class CopyLimited(unittest.TestCase):
    def test_copies_a_stream_within_the_limit(self) -> None:
        sink = io.BytesIO()
        self.assertTrue(gate.copy_limited(io.BytesIO(b"x" * 10), sink, 10))
        self.assertEqual(sink.getvalue(), b"x" * 10)

    def test_stops_once_the_stream_passes_the_limit(self) -> None:
        self.assertFalse(gate.copy_limited(io.BytesIO(b"x" * 11), io.BytesIO(), 10))


class Gate(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.fakes = Fakes(Path(self.directory.name))

    def tearDown(self) -> None:
        self.directory.cleanup()

    def gate(
        self, original: str, stdin: bytes = b"", **fake: str
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["python3", "-I", str(HERE / "gate.py")],
            input=stdin,
            capture_output=True,
            env=self.fakes.env(SSH_ORIGINAL_COMMAND=original, **fake),
            check=False,
        )

    def docker_calls(self) -> list[list[str]]:
        return [c["args"] for c in self.fakes.recorded() if c["program"] == "docker"]

    def test_runs_no_docker_for_a_refused_request(self) -> None:
        result = self.gate("bash -i")
        self.assertEqual(result.returncode, gate.EXIT_USAGE)
        self.assertIn(b"not a request the gate runs", result.stderr)
        self.assertEqual(self.docker_calls(), [])

    def test_refuses_arguments_in_place_of_ssh_original_command(self) -> None:
        result = subprocess.run(
            ["python3", "-I", str(HERE / "gate.py"), "build", "zlib"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=self.fakes.env(),
            check=False,
        )
        self.assertEqual(result.returncode, gate.EXIT_USAGE)
        self.assertEqual(self.docker_calls(), [])

    def test_sync_unpacks_the_stream_into_daily_in_the_container(self) -> None:
        result = self.gate("sync", stdin=b"t" * 4096)
        self.assertEqual(result.returncode, 0, result.stderr)
        state, unpack = self.docker_calls()
        self.assertEqual(state[-2:], ["-", "running"])
        self.assertEqual(unpack[:5], ["exec", "-i", "dojo-builder", "sh", "-c"])
        self.assertIn("tar -xmf - --no-same-owner -C /work/daily.new", unpack[5])
        self.assertEqual(self.fakes.recorded()[-1]["stdin"], 4096)

    def test_build_runs_doj_plan_build_on_the_daily_tree(self) -> None:
        result = self.gate("build zlib", FAKE_BUILD="7")
        self.assertEqual(result.returncode, 7)
        _, check, run = self.docker_calls()
        self.assertEqual(
            check, ["exec", "dojo-builder", "test", "-f", "/work/daily/zlib/plan.fnl"]
        )
        self.assertEqual(
            run,
            [
                "exec",
                "-w",
                "/work/daily",
                "dojo-builder",
                "nice",
                "-n",
                "15",
                "doj-plan-build",
                "build",
                "/work/daily/zlib",
                "--target",
                "x86_64-linux",
            ],
        )

    def test_build_refuses_a_plan_the_tree_lacks(self) -> None:
        result = self.gate("build zlib", FAKE_PLAN="1")
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"holds no plan.fnl", result.stderr)
        self.assertNotIn(
            "doj-plan-build", [w for call in self.docker_calls() for w in call]
        )

    def test_sync_and_build_wait_for_nothing_and_start_nothing_while_something_builds(
        self,
    ) -> None:
        for original in ("sync", "build zlib"):
            with self.subTest(original=original):
                self.fakes.calls.unlink(missing_ok=True)
                result = self.gate(
                    original, stdin=b"t", FAKE_RUNNING=str(gate.EXIT_RUNNING)
                )
                self.assertEqual(result.returncode, gate.EXIT_RUNNING)
                self.assertIn(b"doj-plan-build build /work/plans/gcc", result.stderr)
                self.assertEqual(len(self.docker_calls()), 1)

    def test_an_interrupted_run_does_not_hold_the_daily_build(self) -> None:
        self.assertEqual(self.gate("build zlib", FAKE_RUNNING="4").returncode, 0)

    def test_running_passes_state_on(self) -> None:
        result = self.gate("running", FAKE_RUNNING=str(gate.EXIT_RUNNING))
        self.assertEqual(result.returncode, gate.EXIT_RUNNING)
        self.assertIn(b"process 42", result.stdout)


class Daily(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.fakes = Fakes(Path(self.directory.name))

    def tearDown(self) -> None:
        self.directory.cleanup()

    def daily(self, *plans: str, **env: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [str(HERE / "daily"), *plans],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=self.fakes.env(**env),
            check=False,
        )

    def test_a_scheduled_build_syncs_the_tree_then_builds_each_plan(self) -> None:
        result = self.daily(
            "zlib", "m4", BUILDQ_SOURCE="schedule", DOJO_BUILDER_GATE="owner@localhost"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.fakes.recorded()
        self.assertEqual(
            [c["args"][-2:] for c in calls],
            [["owner@localhost", "sync"], ["build", "zlib"], ["build", "m4"]],
        )
        self.assertGreater(calls[0]["stdin"], 0)
        self.assertIn("BatchMode=yes", calls[0]["args"])

    def test_stops_at_the_first_plan_that_fails(self) -> None:
        result = self.daily(
            "zlib",
            "m4",
            BUILDQ_SOURCE="schedule",
            DOJO_BUILDER_GATE="o@h",
            FAKE_BUILD="5",
        )
        self.assertEqual(result.returncode, 5)
        self.assertEqual(self.fakes.recorded()[-1]["args"][-2:], ["build", "zlib"])

    def test_another_source_cancels_its_own_step_and_reaches_no_gate(self) -> None:
        for source in ("webhook", "api", "ui", "catchup"):
            with self.subTest(source=source):
                self.fakes.calls.unlink(missing_ok=True)
                result = self.daily(
                    "zlib",
                    BUILDQ_SOURCE=source,
                    BUILDQ_STEP_KEY="daily",
                    DOJO_BUILDER_GATE="o@h",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                (call,) = self.fakes.recorded()
                self.assertEqual(call["program"], "buildq-agent")
                self.assertEqual(
                    call["args"][:4], ["step", "cancel", "--step", "daily"]
                )
                self.assertIn(f"this build's source is {source}", call["args"][-1])

    def test_outside_buildq_refuses_and_reaches_no_gate(self) -> None:
        result = self.daily("zlib", DOJO_BUILDER_GATE="o@h")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.fakes.recorded(), [])


if __name__ == "__main__":
    unittest.main()
