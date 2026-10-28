"""Checkpoint identities remain stable across real fresh-process hash seeds."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class IdentityPortabilityTests(unittest.TestCase):
    def environment(self, seed):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("NACRE_GENESIS")}
        environment["PYTHONHASHSEED"] = str(seed)
        return environment

    def test_module_and_runtime_identity_across_fresh_hash_seeds(self):
        source = ('import json; from nacre.identity import module_fingerprint; '
                  'from nacre.runtime import _implementation_digest; '
                  'print(json.dumps([module_fingerprint("nacre.language"),_implementation_digest()]))')
        observations = []
        for seed in (1, 2, 42):
            process = subprocess.run([sys.executable, "-c", source], env=self.environment(seed),
                                     capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
            observations.append(json.loads(process.stdout))
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0], observations[2])

    def test_checkpoint_resume_in_fresh_process_with_different_hash_seed(self):
        with tempfile.TemporaryDirectory(prefix="nacre-seed-checkpoint-") as directory:
            root = Path(directory)
            source = root / "program.nac"
            source.write_text('task first: Number <- core.wait(value=42,milliseconds=1); '
                              'let answer: Number = first + 0; verify answer == 42; emit answer;', encoding="utf-8")
            command = [sys.executable, "-m", "nacre", "run", str(source), "--checkpoint", str(root / "checkpoint.json")]
            first = subprocess.run(command, cwd=root, env=self.environment(1),
                                   capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            second = subprocess.run(command + ["--resume"], cwd=root, env=self.environment(2),
                                    capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            result = json.loads(second.stdout)
            self.assertEqual(result["emitted"], [42])
            self.assertTrue(result["resumed"])
            self.assertEqual(sum(event["event"] == "cache_hit" for event in result["events"]), 2)


if __name__ == "__main__":
    unittest.main()
