import type { DetailSection } from '../../../web/src/lib/matchDetail.ts';
import { LocalTime } from './LocalTime.tsx';

// A match's model detail, section by section (DetailSections.svelte), each row's explanation on hover
export function DetailSections({ sections, notes = [] }: { sections: DetailSection[]; notes?: string[] }) {
	return (
		<>
			{sections.map((sec) => (
				<div className="why-sec" key={sec.title}><div className="why-sec-hd">{sec.title}{sec.unit && <>{' '}<span className="why-unit">{sec.unit}</span></>}</div>
					{sec.rows.map((r) => (
						<div className={`why-row${r.teams ? ' why-teams' : ''}`} title={r.tip} key={r.label}><span>{r.label}</span>
							<b>{typeof r.value === 'string' ? r.value : <><LocalTime iso={r.value.when} show="short" /> <LocalTime iso={r.value.when} show="time" /></>}</b></div>
					))}
					{sec.note && <div className="why-note">{sec.note}</div>}
				</div>
			))}
			{notes.map((n) => <div className="why-note" key={n}>{n}</div>)}
		</>
	);
}
