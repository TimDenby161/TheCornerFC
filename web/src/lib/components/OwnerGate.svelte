<script lang="ts">
	import { openAccount } from '#lib/account.svelte.ts';
	import { owner } from '#lib/owner.svelte.ts';

	// What an owner-only part shows anyone else: a short why, and a way to sign in
	let { label, signedIn, why = "it's built on FPL's own data (prices, positions, availability and gameweeks), which FPL's terms don't allow us to republish" }:
		{ label: string; signedIn: boolean; why?: string } = $props();
</script>

<div class="stats-label">{label}</div>
{#if signedIn && (owner.status === 'idle' || owner.status === 'busy')}
	<div class="stats-note">Loading…</div>
{:else}
	<div class="stats-note">Shown to the site owner only: {why}.</div>
	{#if !signedIn}<div class="mt-lock"><button type="button" class="mt-btn owner-signin" onclick={() => openAccount()}>Sign in</button></div>{/if}
	{#if owner.error && signedIn}<div class="stats-note mt-warn" role="alert">{owner.error}</div>{/if}
{/if}
