// SEO tools' crawlers send no visitors and were using up the free plan's CPU (2026-10-18:
// SemrushBot behind most of 1,823 pages cut off in a day, task T-039). robots.txt asks them to stay
// away, and a Cloudflare WAF rule blocks them. Search engines (Googlebot, Bingbot) are welcome.
// The list is in names.json, which the C# site reads too.
import names from './names.json';

export const SEO_BOTS: string[] = names.SEO_BOTS;
