<script lang="ts">
	import AccountBox from '#lib/components/AccountBox.svelte';

	let { data, form } = $props();
	let title = $state('Your account');
	// a form sent without the page's script comes back here with its answer
	const answer = $derived((form as { message?: string; note?: string } | null)?.message || (form as { note?: string } | null)?.note || data.message);
</script>

<svelte:head><title>{title} · The Corner FC</title><meta name="robots" content="noindex" /></svelte:head>

<section class="panel" data-tab="club" data-active="true">
	<div class="modal-card account-page">
		<div class="modal-header"><div id="account-title">{title}</div></div>
		<div id="account-body">
			<AccountBox user={data.user} sub={data.sub} start={data.view} message={answer} messageOk={data.messageOk && answer === data.message} onview={(t) => (title = t)} />
		</div>
	</div>
</section>
