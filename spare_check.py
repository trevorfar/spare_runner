"""List the Namespace runners created around one GitHub run, and flag spares.

Usage: python3 scripts/spare_check.py <github_run_id>

Assumes nothing else used the same profile during the run, because runners are
matched to the run by time window (instances carry no run-id label).
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

NSC = os.path.expanduser("~/.ns/bin/nsc")


def nsc_json(*args):
    out = subprocess.run([NSC, *args, "-o", "json"], stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out) or []


def ts(s):
    # nsc emits nanosecond timestamps; fromisoformat accepts at most microseconds.
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", s).replace("Z", "+00:00")) if s else None


def main(run_id):
    all_jobs = nsc_json("github", "job", "list", "--since", "24h", "--max_entries", "500")
    jobs = [j for j in all_jobs if j["run_id"] == run_id]
    if not jobs:
        sys.exit(f"no jobs found for run {run_id}")
    other_runners = {j["runner"]["instance_id"]: f"{j['workflow_name']}/{j['job_name']} (run {j['run_id']})"
                     for j in all_jobs if "runner" in j and j["run_id"] != run_id}
    tag = "namespace-profile-" + jobs[0]["profile"]["tag"]
    window_start = min(ts(j["created_at"]) for j in jobs)
    last_start = max(ts(j["started_at"]) for j in jobs)
    window_end = max(ts(j["completed_at"]) for j in jobs)
    job_runners = {j["runner"]["instance_id"]: j["job_name"] for j in jobs if "runner" in j}

    runners = [i for i in nsc_json("instance", "history", "--all", "--since", "24h", "--max_entries", "500")
               if i.get("user_label", {}).get("nsc.runner-profile-tag") == tag
               and window_start <= ts(i["created"]) <= window_end + timedelta(seconds=30)]

    print(f"run {run_id}: {len(jobs)} jobs, {len(runners)} runners, last job started {last_start:%H:%M:%S}")
    for i in sorted(runners, key=lambda i: i["created"]):
        created, destroyed = ts(i["created"]), ts(i.get("destroyed_at"))
        life = f"{(destroyed - created).total_seconds():6.0f}s" if destroyed else "  alive"
        if i["cluster_id"] in job_runners:
            note = "ran " + job_runners[i["cluster_id"]]
        elif i["cluster_id"] in other_runners:
            note = "ran " + other_runners[i["cluster_id"]]
        elif created > last_start:
            note = "SPARE, created after every job had started"
        else:
            note = "SPARE"
        print(f"  {created:%H:%M:%S}  {i['cluster_id']}  life={life}  {note}")


if __name__ == "__main__":
    main(int(sys.argv[1]))
