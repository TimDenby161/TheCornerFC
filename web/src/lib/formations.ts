// The roles in a formation ("4-2-3-1" -> GK LB CB RB DM LW AM RW ST), as positions.py role()
export function formationRoles(f: string): string[] {
	const lines = String(f).split('-').map(Number);
	if (!lines.length || lines.some((n) => !(n > 0))) return [];
	const wide = (n: number, col: number, l: string, m: string, r: string) => (col === 1 ? l : col === n ? r : m);
	const last = lines.length - 1, backThree = lines[0] === 3, middles = last - 1;
	const out = new Set(['GK']);
	lines.forEach((n, idx) => {
		for (let col = 1; col <= n; col++) {
			let r;
			if (idx === 0) r = n === 4 ? wide(n, col, 'LB', 'CB', 'RB') : n === 5 ? wide(n, col, 'LWB', 'CB', 'RWB') : 'CB';
			else if (idx === last) r = n >= 3 ? wide(n, col, 'LW', 'ST', 'RW') : 'ST';
			else if (middles === 1 || idx === 1) {
				if (middles !== 1 && n <= 2) r = 'DM';
				else if (n === 4) r = backThree ? wide(n, col, 'LWB', 'CM', 'RWB') : wide(n, col, 'LM', 'CM', 'RM');
				else if (n === 5) r = wide(n, col, 'LWB', 'CM', 'RWB');
				else r = 'CM';
			} else if (n <= 2) r = idx === last - 1 ? 'AM' : 'CM';
			else if (n === 4) r = wide(n, col, 'LM', 'CM', 'RM');
			else r = wide(n, col, 'LW', 'AM', 'RW');
			out.add(r);
		}
	});
	return [...out];
}
