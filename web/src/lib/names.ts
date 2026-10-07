// Names, short forms and groupings the pages share. Carried over from the old site's app.js.
// prettier-ignore
export const SHORT_NAMES: Record<number, string> = {
  2: "Champions League", 3: "Europa League", 848: "Conference League", 531: "UEFA Super Cup",
  15: "Club World Cup", 45: "FA Cup", 48: "EFL Cup", 46: "EFL Trophy", 47: "FA Trophy",
  528: "Community Shield", 181: "Scottish Cup", 185: "Scottish League Cup",
};
// prettier-ignore
export const CLUB_SHORT: Record<number, string> = {
  157: "Bayern", 50: "Man City", 85: "PSG", 33: "Man Utd", 52: "Palace", 168: "Leverkusen",
  165: "Dortmund", 65: "Nott'm Forest", 530: "Atlético", 569: "Club Brugge", 1393: "Union SG",
  553: "Olympiakos", 167: "Hoffenheim", 169: "Frankfurt", 728: "Rayo", 134: "Athletico-PR",
  1603: "Vancouver", 106: "Brest", 163: "Gladbach", 558: "Spartak", 397: "Midtjylland",
  3402: "Omonia", 651: "Ferencváros", 398: "Nordsjælland", 598: "Crvena Zvezda", 550: "Shakhtar",
  2278: "Chivas", 180: "Heidenheim", 1616: "LAFC", 458: "Argentinos", 571: "Salzburg",
  437: "Rosario", 2932: "Al-Hilal", 450: "Estudiantes", 339: "Legia", 238: "Viseu",
  364: "Djurgården", 3491: "Raków", 473: "Ind. Rivadavia", 1599: "Philadelphia", 2286: "Pumas",
  348: "Pogoń", 563: "Beer Sheva", 438: "Vélez", 1595: "Seattle", 456: "Talleres",
  604: "Maccabi TA", 565: "Young Boys", 632: "U Craiova", 440: "Belgrano", 608: "Hajduk Split",
  478: "Instituto", 733: "Standard", 1604: "NYCFC", 442: "Defensa", 476: "Riestra",
  1596: "San Jose", 782: "Liberec", 1123: "Aris", 185: "Paderborn", 20787: "St. Louis",
  1612: "Minnesota", 4686: "Stockport", 602: "Apollon", 4665: "Racing", 5902: "La Louvière",
  3723: "Hradec", 1079: "Krylia", 350: "Cracovia", 1598: "Orlando", 2432: "Barracas",
  426: "Sparta R'dam", 635: "Dinamo Buc.", 410: "Go Ahead", 1600: "Houston", 2391: "Puskás",
  544: "Deportivo", 455: "Atl. Tucumán", 2314: "San Luis", 1605: "LA Galaxy", 1606: "Salt Lake",
  6813: "Makhachkala", 1065: "Central Córdoba", 1610: "Colorado", 457: "Newell's",
  474: "Sarmiento", 1617: "Portland", 2290: "Querétaro", 333: "Sarpsborg", 345: "Zagłębie",
  657: "Beitar",
};
// prettier-ignore
export const FLAG_CODES: Record<string, string> = Object.assign(Object.create(null), {"Afghanistan": "af", "Albania": "al", "Andorra": "ad", "Bosnia": "ba", "Gibraltar": "gi", "Algeria": "dz", "Angola": "ao", "Antigua and Barbuda": "ag", "Argentina": "ar", "Armenia": "am", "Australia": "au", "Austria": "at", "Azerbaijan": "az", "Barbados": "bb", "Belgium": "be", "Benin": "bj", "Bermuda": "bm", "Bolivia": "bo", "Bosnia and Herzegovina": "ba", "Brazil": "br", "Bulgaria": "bg", "Burkina Faso": "bf", "Burundi": "bi", "Cameroon": "cm", "Canada": "ca", "Cape Verde": "cv", "Central African Republic": "cf", "Chad": "td", "Chile": "cl", "Colombia": "co", "Comoros": "km", "Congo": "cg", "Congo DR": "cd", "Costa Rica": "cr", "Croatia": "hr", "Cuba": "cu", "Curaçao": "cw", "Cyprus": "cy", "Czech Republic": "cz", "Czechia": "cz", "Côte d'Ivoire": "ci", "Denmark": "dk", "Dominican Republic": "do", "Ecuador": "ec", "Egypt": "eg", "El Salvador": "sv", "England": "gb-eng", "Equatorial Guinea": "gq", "Estonia": "ee", "Faroe Islands": "fo", "Finland": "fi", "France": "fr", "French Guiana": "gf", "Gabon": "ga", "Gambia": "gm", "Georgia": "ge", "Germany": "de", "Ghana": "gh", "Great Britain": "gb", "Greece": "gr", "Grenada": "gd", "Guadeloupe": "gp", "Guatemala": "gt", "Guinea": "gn", "Guinea-Bissau": "gw", "Guyana": "gy", "Haiti": "ht", "Honduras": "hn", "Hungary": "hu", "Iceland": "is", "Indonesia": "id", "Iran": "ir", "Iraq": "iq", "Israel": "il", "Italy": "it", "Ivory Coast": "ci", "Jamaica": "jm", "Japan": "jp", "Jordan": "jo", "Kazakhstan": "kz", "Kenya": "ke", "Korea Republic": "kr", "Kosovo": "xk", "Latvia": "lv", "Lebanon": "lb", "Liberia": "lr", "Libya": "ly", "Lithuania": "lt", "Luxembourg": "lu", "Madagascar": "mg", "Malawi": "mw", "Mali": "ml", "Malta": "mt", "Mexico": "mx", "Montenegro": "me", "Montserrat": "ms", "Morocco": "ma", "Mozambique": "mz", "Namibia": "na", "Netherlands": "nl", "New Zealand": "nz", "Niger": "ne", "Nigeria": "ng", "North Macedonia": "mk", "Northern Ireland": "gb-nir", "Norway": "no", "Panama": "pa", "Paraguay": "py", "Peru": "pe", "Poland": "pl", "Portugal": "pt", "Republic of Ireland": "ie", "Romania": "ro", "Russia": "ru", "Rwanda": "rw", "Saudi Arabia": "sa", "Scotland": "gb-sct", "Senegal": "sn", "Serbia": "rs", "Sierra Leone": "sl", "Slovakia": "sk", "Slovenia": "si", "South Africa": "za", "Spain": "es", "Sri Lanka": "lk", "St. Kitts and Nevis": "kn", "St. Lucia": "lc", "Suriname": "sr", "Sweden": "se", "Switzerland": "ch", "Tanzania": "tz", "Thailand": "th", "Togo": "tg", "Trinidad and Tobago": "tt", "Tunisia": "tn", "Turkey": "tr", "Türkiye": "tr", "USA": "us", "Uganda": "ug", "Ukraine": "ua", "Uruguay": "uy", "Uzbekistan": "uz", "Venezuela": "ve", "Wales": "gb-wls", "Zambia": "zm", "Zimbabwe": "zw"});
// prettier-ignore
export const COUNTRY_FIRST: string[] = ["England", "Germany", "Spain", "Italy", "France"];
// prettier-ignore
export const REGIONS: string[] = ["Rest of Europe", "Western Europe", "Eastern Europe", "Scandinavia", "Balkans", "Baltics", "South America", "Africa", "Oceania", "Asia", "North America"];
// prettier-ignore
export const EURO_CUPS: number[] = [2, 3, 848];
// prettier-ignore
export const DOMESTIC_CUPS: number[] = [45, 48, 46, 47, 181, 185];
// prettier-ignore
export const CONTINENTS: string[] = ["Europe", "Africa", "Asia", "Oceania", "South America", "North America"];
// prettier-ignore
export const CLUB_ALIASES: Record<string, string> = {
  "Arsenal": "gunners afc", "Aston Villa": "villa avfc", "Bournemouth": "cherries afcb", "Brentford": "bees",
  "Brighton": "seagulls bhafc brighton and hove albion", "Chelsea": "cfc blues", "Crystal Palace": "palace cpfc eagles",
  "Everton": "efc toffees", "Fulham": "cottagers ffc", "Ipswich": "tractor boys itfc", "Leeds": "lufc leeds united",
  "Leicester": "foxes lcfc", "Liverpool": "lfc reds", "Manchester City": "man city mcfc citizens",
  "Manchester United": "man utd man united mufc red devils", "Newcastle": "toon nufc magpies newcastle united",
  "Nottingham Forest": "forest nffc", "Southampton": "saints", "Sunderland": "safc black cats",
  "Tottenham": "spurs thfc tottenham hotspur", "West Ham": "hammers whufc irons west ham united",
  "Wolves": "wolverhampton wanderers wwfc", "Burnley": "clarets", "Coventry": "sky blues ccfc", "Hull City": "tigers",
  "Middlesbrough": "boro", "Sheffield Utd": "blades sheffield united sufc", "Sheffield Wednesday": "owls swfc",
  "West Brom": "wba baggies albion west bromwich", "QPR": "queens park rangers", "Birmingham": "blues bcfc",
  "Norwich": "canaries ncfc", "Stoke City": "potters", "Derby": "rams", "Millwall": "lions", "Preston": "pne",
  "Swansea": "swans jacks", "Cardiff": "bluebirds", "Portsmouth": "pompey", "Blackburn": "rovers",
  "Charlton": "addicks", "Watford": "hornets", "Bristol City": "robins", "Plymouth": "argyle", "Huddersfield": "terriers",
  "Barcelona": "barca fcb", "Real Madrid": "rmcf los blancos", "Atletico Madrid": "atleti atm", "Athletic Club": "bilbao",
  "Real Sociedad": "la real", "Real Betis": "betis", "Bayern München": "bayern munich fcb", "Borussia Dortmund": "bvb",
  "Borussia Mönchengladbach": "gladbach bmg", "Bayer Leverkusen": "b04", "RB Leipzig": "rbl", "Eintracht Frankfurt": "sge",
  "VfB Stuttgart": "vfb", "Inter": "internazionale inter milan", "AC Milan": "milan acm rossoneri", "Juventus": "juve",
  "AS Roma": "roma", "Paris Saint Germain": "psg paris sg", "Marseille": "om olympique de marseille",
  "Lyon": "ol olympique lyonnais", "Sporting CP": "sporting lisbon scp", "Benfica": "slb", "FC Porto": "porto",
  "PSV Eindhoven": "psv", "Club Brugge KV": "club bruges", "Union St. Gilloise": "usg union saint gilloise",
  "Galatasaray": "gala cimbom", "Fenerbahçe": "fener", "Beşiktaş": "besiktas bjk", "Olympiakos Piraeus": "olympiacos",
};
// prettier-ignore
export const LEAGUE_ALIASES: Record<number, string> = {
  39: "epl pl prem", 40: "champ efl", 41: "l1 league 1 efl", 42: "l2 league 2 efl", 43: "nl non league",
  50: "nln non league", 51: "nls non league", 140: "laliga liga", 141: "segunda liga 2", 135: "serie a", 136: "serie b",
  78: "buli bl", 79: "2 bundesliga zweite", 61: "l1 ligue 1", 62: "l2 ligue 2", 94: "liga portugal", 179: "spfl prem",
  144: "jpl belgian pro league", 203: "super lig", 253: "mls", 71: "brasileirao", 262: "liga mx",
};
// prettier-ignore
export const COUNTRY_ALIASES: Record<string, string> = {
  "England": "uk gb eng", "Scotland": "uk gb sco", "USA": "us united states america", "Netherlands": "holland ned dutch",
  "Czech-Republic": "czechia cze", "Turkey": "turkiye tur", "Spain": "esp", "Germany": "ger deu", "Switzerland": "sui",
  "Croatia": "cro", "Denmark": "den", "Portugal": "por", "Greece": "gre", "Saudi-Arabia": "ksa", "Bosnia": "bih herzegovina",
};
// prettier-ignore
export const PRIMARY_COMPS: { id: string; label: string; ids?: number[] }[] = [
  { id: "eng", label: "English", ids: [39, 40, 41, 42, 43, 50, 51, 45, 46, 47, 48, 528] },
  { id: "39", label: "Prem" }, { id: "40", label: "Champ" }, { id: "41", label: "L1" },
  { id: "42", label: "L2" }, { id: "2", label: "UCL" }, { id: "3", label: "UEL" },
];
// prettier-ignore
export const TABLE_COMPS: { id: string; label: string }[] = [
  { id: "39", label: "Prem" }, { id: "40", label: "Champ" }, { id: "41", label: "L1" },
  { id: "42", label: "L2" }, { id: "140", label: "La Liga" }, { id: "135", label: "Serie A" },
  { id: "78", label: "Bundesliga" }, { id: "61", label: "Ligue 1" },
];
// Every country outside the big five goes under a region; anything not listed is "Rest of Europe"
// (UEFA members such as Turkey, Israel and Kazakhstan included).
// prettier-ignore
const REGION_LISTS: Record<string, string[]> = {
  "Western Europe": ["Portugal", "Netherlands", "Belgium", "Scotland", "Switzerland", "Austria", "Andorra", "Gibraltar",
    "Ireland", "Northern Ireland", "Wales", "Luxembourg", "Malta"],
  "Eastern Europe": ["Czech Republic", "Hungary", "Poland", "Russia", "Slovakia", "Ukraine", "Belarus", "Moldova"],
  "Scandinavia": ["Denmark", "Norway", "Sweden", "Finland", "Iceland"],
  "Balkans": ["Albania", "Bosnia", "Bulgaria", "Croatia", "Greece", "Kosovo", "Montenegro", "North Macedonia", "Romania", "Serbia", "Slovenia"],
  "Baltics": ["Estonia", "Latvia", "Lithuania"],
  "South America": ["Argentina", "Brazil", "Chile", "Colombia", "Uruguay", "Paraguay", "Peru", "Ecuador", "Bolivia", "Venezuela"],
  "Africa": ["Egypt", "Morocco", "South Africa", "Nigeria", "Tunisia", "Algeria", "Ghana", "Senegal", "Ivory Coast", "Cameroon", "Kenya", "Tanzania", "Zambia"],
  "Oceania": ["Australia", "New Zealand", "Fiji"],
  "Asia": ["Saudi Arabia", "Japan", "South Korea", "China", "Qatar", "United Arab Emirates", "Iran", "Iraq", "India", "Thailand", "Vietnam", "Indonesia", "Malaysia", "Uzbekistan", "Kuwait", "Bahrain", "Oman", "Jordan"],
  "North America": ["USA", "Mexico", "Canada", "Costa Rica", "Honduras", "Guatemala", "Jamaica", "Panama", "El Salvador"],
};
const REGION_OF: Record<string, string> = {};
for (const [region, list] of Object.entries(REGION_LISTS)) for (const c of list) REGION_OF[c] = region;
export const regionOf = (country: string) => REGION_OF[country] || 'Rest of Europe';
// chip labels: "N. America", "S. America" (the full name stays in the key, links and hover text)
export const regionLabel = (r: string) => r.replace(/^(North|South) America$/, (m, d) => `${d[0]}. America`);
export const continentOf = (country: string) => {
	const region = COUNTRY_FIRST.includes(country) ? 'Europe' : regionOf(country);
	return CONTINENTS.includes(region) ? region : 'Europe'; // the European regions
};
