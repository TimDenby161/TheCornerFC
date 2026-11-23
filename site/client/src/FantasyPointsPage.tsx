// The Fantasy points page (/fantasy-points, T-104): every Premier League player's expected points
// by round, for any signed-in account. The same table as the owner's FPL page without the owner's
// ticks (Mine, Target), and without the game's name (owner's decision 2026-11-23).
import { Predictions } from './FplPage.tsx';
import { usePoints } from './owner.ts';

export function FantasyPointsPage({ email }: { email: string | null }) {
	const owner = usePoints(email);
	return <div id="points-body">
		{owner.points !== 'ok'
			? <div className="stats-card"><div className="stats-label">Expected points</div>
				{email && (owner.points === 'idle' || owner.points === 'busy')
					? <div className="stats-note">Loading…</div>
					: <>
						<div className="stats-note">Every Premier League player's expected fantasy points for each of the next 10 rounds, with price, position and injury news. Free with an account.</div>
						{!email && <div className="mt-lock"><a role="button" className="mt-btn owner-signin" href="/account?view=signin">Sign in free</a></div>}
						{email && <div className="stats-note mt-warn" role="alert">{owner.error || "Couldn't load the points just now."}</div>}
					</>}
			</div>
			: <>
				<Predictions owner={owner} marking={false} />
				<div className="stats-card">
					<div className="stats-label">How the points are worked out</div>
					<div className="stats-note">Each player's points are our model's prediction for his position under the usual fantasy scoring: minutes, goals, assists,
						clean sheets, goals conceded, saves, penalties, cards, bonus and defensive contributions. Goals come from our match predictions, shared out by each
						player's shots and chances; minutes from how often he starts and how long he plays; injured and suspended players count as out until they are due back,
						and doubtful ones at their chance of playing. Prices, positions and injury news are updated every night. Click a player's points to see where they come from.
						In the multi-round view, capitals are home games and lower case away. Further ahead assumes today's form and fitness: a guide, not a pick list.</div>
					<div className="stats-note">The Corner FC is not affiliated with the Premier League or any fantasy football game.</div>
				</div>
			</>}
	</div>;
}
