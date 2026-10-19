import { crestHue, crestInitials } from '../../../web/src/lib/site.ts';

// A club's chip: its initials on a colour of its own (Crest.svelte), hidden from screen readers
export function Crest({ id, name }: { id: number; name: string }) {
	return <span className={`club-logo crest crest-h${crestHue(id)}`} title={name} aria-hidden="true"><b>{crestInitials(name, true)}</b></span>;
}
