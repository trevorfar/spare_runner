When jobs are pinned to their workflow run with github.run-id, namespace still starts an extra runner for each job. (From my limited testing, about 2-3s after the job already started on its own runner). Since they are pinned to specific jobids, the runner can only take jobs from that run, and they all have runners (by construction) which means they are dangling runners. 

Docs say one runner per job: 
https://namespace.so/docs/workspaces/billing-and-limits#am-i-billed-for-runner-instances-that-do-not-pick-up-a-job
"Namespace starts a runner instance for every scheduled GitHub Actions job" (Billing and Limits FAQ, "Am I billed for runner instances that do not pick up a job?")

https://namespace.so/docs/solutions/github-actions/runner-controls/job-ordering
"To control this behaviour, you can add the run id to the labels. Then only that specific job can be picked up by the runner started for it" (Runner controls, "Deterministic assignments")

Environment:
Workspace fk6i2lgo4qhe0, region iad3
Runner profile: benchmark
Specs:
Linux amd64 4x8, Ubuntu 24.04, 50 GB cache volume


Steps to reproduce:
1) Create github repo
2) Add a workflow linked to run ids. Example:

name: spare-repro
on:
  workflow_dispatch:
jobs:
  pinned:
    strategy:
      matrix:
        n: [1, 2, 3]
    runs-on: namespace-profile-benchmark;github.run-id=${{ github.run_id }}
    steps:
      - run: sleep 30

3)  (github): Actions -> <spare-repro> -> run workflow. Keep the runid for our little python script. Wait ~7m from my testing for the dangling runners to self-destruct.

4) List the jobs and the runners that ran them. 2 options:
	1) Got AI to make a python script ( easiest)
		1.1) Copy the runid from github:
			https://github.com/trevorfar/spare_runner/actions/runs/<RUN_ID>
		1.2) python spare_check.py <RUN_ID>
			run <RUN_ID>: 3 jobs, 6 runners, last job started 16:20:32
			  16:20:10  ftibs2qmi6oag  life=    76s  ran pinned (2)
			  16:20:10  80laplqo7uup2  life=    74s  ran pinned (3)
			  16:20:10  bvq55p4f8e98o  life=    78s  ran pinned (1)
			  16:20:34  l31frpgrvi6fq  life=   442s  SPARE, created after every job had started
			  16:20:35  13cun8mfcu1jq  life=   441s  SPARE, created after every job had started
			  16:20:35  918ossr7v1u5u  life=   441s  SPARE, created after every job had started

	2) Can use nsc commands:
		2.1) nsc github job list --since 1h -o json
		2.2) nsc instance history --all --since 1h -o json
		2.3) Compare the two. Count the instances with user_label["nsc.runner-profile-tag"] == "namespace-profile-<profile>" created during the run, and the runner.instance_id values that are in the job list


Notes:
	This is intermittent but pretty common, on this writeup it happened 3/3 times. I did 22 pinned jobs a bit ago and 12 occured, each idling for 5-8 minutes.


Impact:
	This is a pretty small fix. Each extra runner holds a 4x8 VM for ~7 minutes. For the 3 jobs, thats around 22 minutes of idle VM-minutes contrasted against 4m of actual work. According to the docs these aren't billed (Haven't verified), so the cost falls on you guys. Another impact is possibly the concurrency limit? Since we have dangling runners taking up jobs this could delay based on that.
