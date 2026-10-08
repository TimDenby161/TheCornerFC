// Each section's line of introduction and what its figures mean, carried over from the old site's
// app.js. `more`: the part of the methodology page that explains it.
export type TabInfo = { intro: string; more: string; key: [string, string][] };
// prettier-ignore
export const TAB_INFO: Record<string, TabInfo> = {
	"clubs": {
		"intro": "Every club ranked by strength, on a scale where 100 points is worth about a goal a game.",
		"more": "terms",
		"key": [
			[
				"Baseline (Base)",
				"A club's long-term level: its rating averaged over roughly its last 100 matches. Slow to move."
			],
			[
				"Current",
				"Its rating after its latest match. It rises when the club does better than expected, and falls when it does worse."
			],
			[
				"Gap",
				"Current minus Baseline. Green: playing above its usual level. Red: below it."
			],
			[
				"Last 6",
				"How far its rating has moved over its last 6 matches."
			],
			[
				"World",
				"Its place among every ranked club, by Baseline."
			],
			[
				"In lg",
				"Its place among the clubs in its own league, by Baseline. This is the site's ranking, not the league table."
			]
		]
	},
	"players": {
		"intro": "Players ranked by Ability, the model's 0 to 100 estimate of how good each one is now.",
		"more": "terms",
		"key": [
			[
				"Ability",
				"A 0 to 100 estimate of his level, from the clubs he plays for and his own statistics. An average Premier League regular is about 75. The + shows past and projected seasons."
			],
			[
				"Pos",
				"The role he has started in most over his last 20 appearances."
			],
			[
				"World",
				"His place by Ability among every listed player."
			],
			[
				"Lg",
				"His place by Ability among the listed players in his club's league."
			],
			[
				"G/A",
				"Goals and assists this season, for all his clubs."
			]
		]
	},
	"leagues": {
		"intro": "Leagues ranked by the average strength of their clubs this season.",
		"more": "terms",
		"key": [
			[
				"Baseline (Base)",
				"The average long-term rating of the league's clubs."
			],
			[
				"Current",
				"The average of its clubs' ratings now."
			],
			[
				"Gap",
				"Current minus Baseline. Green: its clubs are rated above their long-term level. Red: below it."
			]
		]
	},
	"nations": {
		"intro": "National teams ranked by strength, worked out from every men's full international since 1872.",
		"more": "terms",
		"key": [
			[
				"Current",
				"The team's rating now. 100 points is about one goal a game on a neutral ground."
			],
			[
				"1 yr",
				"How far its rating has moved over the last 12 months."
			],
			[
				"UEFA, CAF …",
				"The confederation it plays in. The buttons above the table show one at a time."
			]
		]
	},
	"matches": {
		"intro": "Fixtures and results, with the model's chance of a home win, a draw and an away win for each match.",
		"more": "terms",
		"key": [
			[
				"The bar",
				"The model's chances of a home win, a draw and an away win, as percentages."
			],
			[
				"Market",
				"The bookmakers' chances for the same match: their odds with the bookmaker's margin taken out, averaged across bookmakers."
			],
			[
				"Projected goals",
				"The goals the model expects each side to score, such as 1.6–0.9. An average over many possible games, not a score prediction."
			],
			[
				"The number by each club",
				"Its Current Strength."
			]
		]
	},
	"stats": {
		"intro": "How accurate the model's match predictions have been, and how they compare with the bookmakers'. Club and national team matches together: pick a competition to see one on its own.",
		"more": "glossary",
		"key": [
			[
				"Log loss",
				"Punishes the model for being confident and wrong. Lower is better. Giving every result a one-in-three chance scores 1.099."
			],
			[
				"Brier score",
				"The average squared gap between the chances given and what happened. Lower is better. One-in-three for everything scores 0.667."
			],
			[
				"Goal error",
				"How many goals out the projected score was, on average, for each team."
			],
			[
				"Market fair",
				"The bookmakers' chances with their margin taken out, averaged across bookmakers, from the last odds before kick-off."
			],
			[
				"Gap",
				"The model's log loss minus the market's. Green (below zero): the model was more accurate. Red: the market was."
			],
			[
				"Gap at opening",
				"The same comparison against the first odds recorded for each match, with the number of matches in brackets."
			]
		]
	},
	"lineups": {
		"intro": "How often the line-ups the model predicted matched the team sheets.",
		"more": "lineups",
		"key": [
			[
				"Saved before kick-off",
				"Predictions stored before the team sheet came out. The only fair test."
			],
			[
				"Reconstructed history",
				"The model run again on past matches, using what was known before each one. A guide, not proof."
			],
			[
				"Perfect XIs",
				"Line-ups where all 11 starters were predicted."
			]
		]
	},
	"tips": {
		"intro": "Upcoming selections where the model and the bookmakers disagree most. A disagreement isn't a tip: so far the bookmakers have been right more often.",
		"more": "market",
		"key": [
			[
				"Markets",
				"The kinds of bet compared: the result, over or under a number of goals, and both teams to score."
			],
			[
				"Market fair",
				"The bookmakers' chance for the selection, with their margin taken out."
			],
			[
				"Beat closing price",
				"The share of selections recorded at better odds than the last price before kick-off."
			],
			[
				"Strike rate",
				"The share of settled selections that won."
			]
		]
	},
	"bets": {
		"intro": "A record of those selections as if each had been backed with the same paper stake. No real money is involved.",
		"more": "market",
		"key": [
			[
				"Night before",
				"Selections recorded by the nightly update."
			],
			[
				"Pre-kickoff",
				"Selections recorded shortly before kick-off, after late team news."
			],
			[
				"Cautious",
				"The same record without result bets on outsiders."
			],
			[
				"O/U 2.5",
				"Over or under 2.5 goals in the match. 1.5, 3.5 and 4.5 work the same way."
			],
			[
				"Both score",
				"Whether both teams score."
			]
		]
	},
	"efl": {
		"intro": "Expected Fantasy EFL points for Championship, League One and League Two players and clubs.",
		"more": "",
		"key": [
			[
				"Pts",
				"The points the model expects in that gameweek."
			],
			[
				"CS",
				"The chance of a clean sheet."
			],
			[
				"G, D, M, F",
				"Goalkeeper, defender, midfielder, forward. A * means the position is the site's guess from match data."
			],
			[
				"Ch, L1, L2",
				"Championship, League One, League Two."
			],
			[
				"1-2-3-1",
				"A team's shape: one goalkeeper, then defenders, midfielders and forwards."
			]
		]
	},
	"fpl": {
		"intro": "Expected Fantasy Premier League points. Shown to the site owner only.",
		"more": "",
		"key": []
	},
	"myteam": {
		"intro": "The site owner's own Fantasy Premier League team and transfer plan.",
		"more": "",
		"key": []
	}
};
