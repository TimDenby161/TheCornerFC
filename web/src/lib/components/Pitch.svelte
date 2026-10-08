<script lang="ts">
	import type { Snippet } from 'svelte';

	// A pitch, in the club's home kit colours where its file has them (stripes in the shirt colour,
	// lines in the number colour); otherwise the plain dark pitch. `kind` is the stylesheet's class
	// for what stands on it.
	let { kind, kit = null, children }: { kind: string; kit?: string[] | null; children: Snippet } = $props();
	// the colours are the club's own, so they can't be classes: set once the page is running
	function colours(node: HTMLElement, kit: string[] | null) {
		const set = (k: string[] | null) => { if (k) { node.style.setProperty('--kit', `#${k[0]}`); node.style.setProperty('--kit2', `#${k[1]}`); } };
		set(kit);
		return { update: set };
	}
</script>

<div class="pitch {kind}" class:kit={!!kit} use:colours={kit}>
	<svg viewBox="0 0 68 88" preserveAspectRatio="none" aria-hidden="true" fill="none" stroke="rgba(255,255,255,0.16)" stroke-width="0.6">
		<rect x="3" y="3" width="62" height="82" rx="1" /><line x1="3" y1="44" x2="65" y2="44" />
		<circle cx="34" cy="44" r="7" /><rect x="17" y="3" width="34" height="12" /><rect x="26" y="3" width="16" height="5" />
		<rect x="17" y="73" width="34" height="12" /><rect x="26" y="80" width="16" height="5" /></svg>
	{@render children()}
</div>
