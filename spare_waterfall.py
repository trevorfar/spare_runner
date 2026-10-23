"""Discover registered spares and give each an exact-runner routing label."""
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def api(path, *, token, body=None):
    request = Request(
        os.environ.get("GITHUB_API_URL", "https://api.github.com") + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def pages(path, key, token):
    result = []
    for page in range(1, 101):
        batch = api(f"{path}?per_page=100&page={page}", token=token)[key]
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise RuntimeError("Pagination limit reached; refusing an incomplete snapshot")


def output(key, value):
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        stream.write(f"{key}={json.dumps(value, separators=(',', ':'))}\n")


def candidates(runners, baseline, used, run_id):
    result = []
    for runner in runners:
        # Namespace may expose the runs-on string as a compound label.
        labels = {part for label in runner["labels"]
                  for part in label["name"].split(";")}
        if (runner["id"] not in baseline | used
                and runner["status"] == "online" and not runner["busy"]
                and "namespace-profile-test" in labels
                and f"github.run-id={run_id}" in labels):
            result.append(runner)
    return sorted(result, key=lambda runner: runner["id"])


def main(mode):
    token = os.environ.get("RUNNER_ADMIN_TOKEN")
    if not token:
        raise RuntimeError("Set RUNNER_ADMIN_TOKEN to a token with repository Administration: write")
    root = f"/repos/{os.environ['GITHUB_REPOSITORY']}/actions"
    runner_path = root + "/runners"
    if mode == "snapshot":
        output("baseline", [r["id"] for r in pages(runner_path, "runners", token)])
        return
    if mode != "discover":
        raise ValueError("Expected snapshot or discover")

    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    baseline = set(json.loads(os.environ["BASELINE"]))
    deadline = time.monotonic() + 120
    ready_since = None
    selected = []
    while time.monotonic() < deadline:
        jobs = pages(f"{root}/runs/{run_id}/attempts/{attempt}/jobs",
                     "jobs", os.environ["GH_TOKEN"])
        seeds = [j for j in jobs if j["name"] in {"seed (1)", "seed (2)", "seed (3)"}]
        # Never mistake a seed runner waiting to accept its job for a spare.
        ready = len(seeds) == 3 and all(j["status"] == "in_progress" and j.get("runner_id") for j in seeds)
        if ready:
            if ready_since is None:
                ready_since = time.monotonic()
            runners = pages(runner_path, "runners", token)
            used = {j["runner_id"] for j in jobs if j.get("runner_id")}
            selected = candidates(runners, baseline, used, run_id)
            print(f"Three seeds running; {len(selected)} online SPARE(s)", flush=True)
            # Collect late registrations without waiting out their idle lifetime.
            if selected and time.monotonic() - ready_since >= 30:
                break
        else:
            ready_since = None
            selected = []
        time.sleep(5)

    if ready_since is None:
        raise RuntimeError("The three seed jobs were not running together before discovery timed out")
    targets = []
    for runner in selected:
        current = api(f"{runner_path}/{runner['id']}", token=token)
        if not candidates([current], baseline, used, run_id):
            continue
        label = f"spare-target-{run_id}-{attempt}-{runner['id']}"
        api(f"{runner_path}/{runner['id']}/labels", token=token, body={"labels": [label]})
        targets.append({"id": runner["id"], "name": runner["name"], "label": label})
        print(f"SPARE id={runner['id']} name={runner['name']} label={label}", flush=True)
    output("targets", targets)
    output("count", len(targets))
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
        summary.write(f"Discovered {len(targets)} SPARE runners.\n\n```json\n")
        summary.write(json.dumps(targets, indent=2) + "\n```\n")
    if not targets:
        print("No live spares discovered; consumer workflow will be skipped.", flush=True)


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except HTTPError as error:
        sys.exit(f"GitHub API returned HTTP {error.code}. Check RUNNER_ADMIN_TOKEN permissions and runner availability.")
