<script lang="ts">
	import { openAccount } from '#lib/account.svelte.ts';
</script>

<!-- (a link to the account page where the page's script isn't running) -->
<a class="link-btn" href="/account?view=subscribe" onclick={(e) => { e.preventDefault(); openAccount('subscribe'); }}>What subscribers get</a>
