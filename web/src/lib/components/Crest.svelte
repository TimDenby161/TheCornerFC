<script lang="ts">
	import { crestHue, crestInitials } from '#lib/site.ts';

	// A club's or competition's chip: its initials on a colour of its own (no badges or logos:
	// those are trade marks). `size` is the stylesheet's class for it; with `href` it opens that
	// page; with `label` it is read out, otherwise it is hidden from screen readers.
	let { id, name, size = 'club-logo', league = false, href, label, title = name }:
		{ id: number; name: string; size?: string; league?: boolean; href?: string; label?: string; title?: string } = $props();
	const hue = $derived(crestHue(league ? id + 7 : id));
	const text = $derived(crestInitials(name, !league));
</script>

{#if href}<a class="{size} crest crest-h{hue}" {href} {title} aria-label={label ?? name}><b>{text}</b></a>{:else}<span class="{size} crest crest-h{hue}" {title} role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : 'true'}><b>{text}</b></span>{/if}
