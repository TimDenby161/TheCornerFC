using TheCornerFC.Web.Data;

namespace TheCornerFC.Web.Site;

// The Skills part of a player's page (owner, 2026-10-21, T-059): his 0 to 100 score in each skill
// and how much each counts in his position's rank, from the model's own table of mixes (the site
// document's skill_mix, player_ratings.SKILL_MIX). Keepers have no outfield skills. A player
// outside the free slice, for a visitor without a subscription, shows the mix without his scores,
// as his ranks are hidden.
public static class PlayerSkills
{
    public sealed record Line(string Key, string Label, string Tip, int Weight, double? Score, int Bar);
    public sealed record View(string Group, string GroupName, List<Line> Lines, bool Locked, bool Scored)
    {
        // "a centre-back", "an attacking mid"
        public string AGroup => $"{("aeiou".Contains(GroupName[0]) ? "an" : "a")} {GroupName}";
    }

    public static View? Of(Player p, SiteDoc site)
    {
        var group = p.Position is { } pos ? Names.GroupOf.GetValueOrDefault(pos) : null;
        var scores = p.Locked ? null : p.Skills;
        if (group == "GK")
        {
            // keepers' own three (MC-0037), with the share of his rank where one counts: his rank
            // uses save % and pass accuracy, and goals conceded per 90 rather than goals prevented
            var keeper = Players.KeeperSkills.Select(k =>
            {
                double? score = scores is not null && scores.TryGetValue(k.Key, out var v) ? v : null;
                var weight = k.Key switch { "shot_stopping" => 50, "distribution" => 25, _ => 0 };
                return new Line(k.Key, k.Label, k.Tip, weight, score, score is { } sc ? Math.Clamp(Js.RoundInt(sc), 0, 100) : 0);
            }).ToList();
            return new("GK", Names.GroupSingle.GetValueOrDefault("GK") ?? "goalkeeper", keeper, p.Locked, keeper.Any(l => l.Score is not null));
        }
        if (group is null || site.SkillMix?.GetValueOrDefault(group) is not { Count: > 0 } mix) return null;
        // every outfield skill, the heaviest in his position's mix first (some weigh nothing in it)
        var lines = Players.Skills
            .Select(s => (s, w: mix.GetValueOrDefault(s.Key)))
            .OrderByDescending(x => x.w).ThenBy(x => Array.IndexOf(Players.Skills, x.s))
            .Select(x =>
            {
                double? score = scores is not null && scores.TryGetValue(x.s.Key, out var v) ? v : null;
                return new Line(x.s.Key, x.s.Label, x.s.Tip, Js.RoundInt(100 * x.w), score, score is { } sc ? Math.Clamp(Js.RoundInt(sc), 0, 100) : 0);
            })
            .ToList();
        return new(group, Names.GroupSingle.GetValueOrDefault(group) ?? group, lines, p.Locked, lines.Any(l => l.Score is not null));
    }
}
