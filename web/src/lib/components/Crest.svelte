<script lang="ts">
	import { crestHue, crestInitials } from '#lib/site.ts';

	// A club's chip: its initials on a colour of its own. `size` is the stylesheet's class for it.
	let { id, name, size = 'club-logo' }: { id: number; name: string; size?: string } = $props();
</script>

<span class="{size} crest crest-h{crestHue(id)}" title={name} aria-hidden="true"><b>{crestInitials(name, true)}</b></span>
