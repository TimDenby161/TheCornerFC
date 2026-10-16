// The timer: a Cloudflare Worker with no address of its own that starts the scheduled jobs on the
// minute, because GitHub's own schedules are late or dropped (2026-10-16: the 01:17 nightly
// started about 06:00, and match day ran 4.6 times a day instead of 48). Each tick asks GitHub to
// run the workflow on main ("Run workflow", with source=timer). GitHub's schedules stay as the
// back-up, and each job skips a slot another run has already done (scripts/already_ran.py), so a
// job never works twice.
//
// One secret, GITHUB_TOKEN: a fine-grained token for this repository only, with Actions read and
// write and nothing else. All it can do is start these jobs, which then skip if there's no work.

export const REPO = 'TimDenby161/TheCornerFC';

// each Cron Trigger in wrangler.jsonc, and the workflow it starts (the same times as each
// workflow's own schedule, which tests/test_workflows.py checks)
export const JOBS = {
	'17 1 * * *': 'nightly.yml',
	'*/30 * * * *': 'matchday.yml',
	'0 7,13,19 * * *': 'fpl.yml'
};

export function dispatchRequest(workflow, token) {
	return new Request(`https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`, {
		method: 'POST',
		headers: {
			authorization: `Bearer ${token}`,
			accept: 'application/vnd.github+json',
			'x-github-api-version': '2022-11-28',
			'content-type': 'application/json',
			'user-agent': 'thecornerfc-timer'
		},
		body: JSON.stringify({ ref: 'main', inputs: { source: 'timer' } })
	});
}

export default {
	async scheduled(controller, env) {
		const workflow = JOBS[controller.cron];
		if (!workflow) return console.error('No job for', controller.cron);
		const response = await fetch(dispatchRequest(workflow, env.GITHUB_TOKEN));
		// GitHub answers 204 when the run is queued. Either way one line goes to the Worker's log
		// (Observability), never anywhere a visitor could see it
		if (response.status === 204) console.log(workflow, 'started');
		else console.error(workflow, response.status, (await response.text()).slice(0, 300));
	},
	// nothing to visit
	async fetch() {
		return new Response('Not found', { status: 404 });
	}
};
