import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spare_waterfall as waterfall


def runner(runner_id, **changes):
    value = {"id": runner_id, "name": f"instance-{runner_id}",
             "status": "online", "busy": False,
             "labels": [{"name": "namespace-profile-test;github.run-id=42"}]}
    return value | changes


class DiscoveryTests(unittest.TestCase):
    def test_excludes_busy_offline_old_assigned_and_other_runs(self):
        runners = [runner(1), runner(2), runner(3), runner(4, busy=True),
                   runner(5, status="offline"),
                   runner(6, labels=[{"name": "namespace-profile-test;github.run-id=420"}]),
                   runner(7, labels=[{"name": "namespace-profile-test"},
                                     {"name": "github.run-id=42"}])]
        self.assertEqual([r["id"] for r in waterfall.candidates(runners, {1}, {2}, "42")], [3, 7])

    def test_discovery_labels_only_spares_after_seeds_are_assigned(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"RUNNER_ADMIN_TOKEN": "test-admin", "GH_TOKEN": "test-actions",
                   "GITHUB_REPOSITORY": "owner/repo", "GITHUB_RUN_ID": "42",
                   "GITHUB_RUN_ATTEMPT": "2", "BASELINE": "[9]",
                   "GITHUB_OUTPUT": f"{directory}/output",
                   "GITHUB_STEP_SUMMARY": f"{directory}/summary"}
            elapsed = [0]
            mutations = []

            def sleep(seconds):
                elapsed[0] += seconds

            def pages(path, key, token):
                if key == "jobs":
                    self.assertIn("/attempts/2/jobs", path)
                    # An online but idle seed is visible before assignment.
                    return [{"name": f"seed ({i})", "runner_id": i if elapsed[0] else 0,
                             "status": "in_progress" if elapsed[0] else "queued"}
                            for i in range(1, 4)]
                return [runner(i) for i in (1, 2, 3, 4, 9)]

            def api(path, *, token, body=None):
                if body:
                    mutations.append((path, body))
                    return {}
                return runner(4)

            with patch.dict(os.environ, env), patch.object(waterfall, "pages", pages), \
                    patch.object(waterfall, "api", api), \
                    patch.object(waterfall.time, "monotonic", lambda: elapsed[0]), \
                    patch.object(waterfall.time, "sleep", sleep):
                waterfall.main("discover")
            outputs = dict(line.split("=", 1) for line in Path(env["GITHUB_OUTPUT"]).read_text().splitlines())
            targets = json.loads(outputs["targets"])
            self.assertEqual([target["id"] for target in targets], [4])
            self.assertEqual(outputs["count"], "1")
            self.assertEqual(mutations, [("/repos/owner/repo/actions/runners/4/labels",
                                         {"labels": ["spare-target-42-2-4"]})])
            self.assertGreaterEqual(elapsed[0], 35)


if __name__ == "__main__":
    unittest.main()
