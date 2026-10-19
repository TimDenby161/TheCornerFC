// SEO tools' crawlers send no visitors and were using up the free plan's CPU (2026-10-18:
// SemrushBot behind most of 1,823 pages cut off in a day, task T-039). robots.txt asks them to stay
// away, and a Cloudflare WAF rule blocks them. Search engines (Googlebot, Bingbot) are welcome.
export const SEO_BOTS = ['SemrushBot', 'AhrefsBot', 'MJ12bot', 'DotBot', 'DataForSeoBot', 'BLEXBot'];
