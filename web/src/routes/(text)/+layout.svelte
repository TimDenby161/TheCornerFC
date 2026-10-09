<script lang="ts">
	// The plain text pages: the site's look without the menu. Ruled, not boxed.
	import '../../styles/page.css';

	let { children } = $props();
</script>

<!-- (a link from here to one of the site's own pages loads it afresh, leaving this stylesheet behind) -->
<main data-sveltekit-reload>{@render children()}</main>
