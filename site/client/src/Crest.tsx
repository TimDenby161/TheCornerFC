import { crestHue, crestInitials } from '../../../web/src/lib/site.ts';

// A club's chip: its initials on a colour of its own (Crest.svelte). With `href` it opens that
// club's page; otherwise it is hidden from screen readers.
export function Crest({ id, name, href, size = 'club-logo' }: { id: number; name: string; href?: string; size?: string }) {
	const cls = `${size} crest crest-h${crestHue(id)}`, text = <b>{crestInitials(name, true)}</b>;
	return href
		? <a className={cls} href={href} title={name} aria-label={name}>{text}</a>
		: <span className={cls} title={name} aria-hidden="true">{text}</span>;
}
