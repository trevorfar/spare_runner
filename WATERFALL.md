# Target a live spare runner

Pushing to `spare-runner-waterfall` starts the experiment automatically, so it
can be tested without merging into the default branch. Once the workflow exists
on the default branch, **Actions → spare-waterfall → Run workflow** is also
available.

First add a repository Actions secret named `RUNNER_ADMIN_TOKEN`: a fine-grained
PAT scoped to this repository with **Administration: read and write**. The
ordinary `GITHUB_TOKEN` cannot administer runner labels. Discovery uses that
ordinary token separately for reading jobs; the consumer receives neither token.

The sequence is:

1. A GitHub-hosted job checks runner API access and snapshots existing runner IDs.
2. Three Namespace jobs start on `namespace-profile-test;github.run-id=<run>`
   and sleep for 180 seconds. Namespace may create N extra runners; N can be zero.
3. A GitHub-hosted discovery job runs alongside the seeds. It waits until all
   three have runners, allows 30 seconds for spare registrations, and selects
   online, idle runners with this profile and exact run label. It excludes the
   initial snapshot and all runners assigned to jobs in this attempt. Discovery
   stops after roughly two minutes if no spares appear.
4. It adds a unique `spare-target-<run>-<attempt>-<runner-id>` label to each
   selected runner, prints `SPARE id=… name=…`, and puts the list in the job
   summary. Existing labels are preserved.
5. `spare-consume.yml` receives the list and schedules one matrix job per spare,
   using only that spare's unique label. Each job verifies `runner.name` against
   the selected runner, then prints its GitHub runner ID, runner name, Namespace
   instance ID (`hostname`), and `SUCCESS`.

The second file is a **reusable workflow in the same run**, called as soon as
discovery finishes, without waiting for the three seeds. This preserves the live
handoff and avoids a dispatch token or waiting for `workflow_run: completed`.
It does not test whether Namespace permits reuse across separate workflow runs.
The original `spare-repro.yml` remains available for the minimal reproduction.

GitHub's numeric runner ID is different from Namespace's instance ID. Discovery
prints the registered runner name without assuming it equals the instance ID;
the consumer prints the actual instance ID. No time-window inference or Namespace
CLI credentials are needed for discovery.

This is an experiment: the first live run must confirm that Namespace exposes
the run/profile labels through GitHub and accepts label changes on these runners.
If no matching spares appear, the consumer is skipped with an explicit message.
If Namespace removes a spare before its job starts, that job can remain queued:
`timeout-minutes` limits execution, not queue time. Cancel the run if that happens.
Late spares created after the discovery snapshot are not included in this wave.

Local checks: `python3 -m unittest -v test_spare_waterfall.py`.

References: [GitHub runner routing](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow),
[runner label API and permissions](https://docs.github.com/en/rest/actions/self-hosted-runners#add-custom-labels-to-a-self-hosted-runner-for-a-repository),
[reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).
