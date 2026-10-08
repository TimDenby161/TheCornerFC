// What fplPlanner.js takes and gives (the code itself is the old site's, unchanged).
import type { PredDoc, TeamDoc, Chip } from './fantasy.ts';

export type Pos = 'G' | 'D' | 'M' | 'F';
export type Move = { out: number; in: number };
export type PlanPlayer = {
	id: number; name: string; pos: Pos; team: number | string; price: number; status?: string | null; chance?: number | null;
	fpl?: number; missing?: boolean; xp: number[]; fixtures: { opponent: number; home: boolean }[][]; rem: number[];
};
export type SquadState = { squad: number[]; sell: Record<number, number>; bank: number };
export type Ctx = { weeks: { id: number; first_kickoff: string; idx: number }[]; H: number; players: Map<number, PlanPlayer>; pool: Record<Pos, PlanPlayer[]> };
export type Prep = { ctx: Ctx; start: SquadState };
export type Lineup = { xi: number[]; bench: number[]; captain: number; vice: number; points: number; captainPts: number; benchPts: number; score: number };
export type PlanWeek = SquadState & { k: number; gw: number; moves: Move[]; hits: number; ft: number; lineup: Lineup; points: number };
export type Plan = { weeks: PlanWeek[]; total: number; hold: number };
export type ChipOption = { k: number; gw: number; gain: number; squad?: number[] };
export type ChipAdvice = {
	name: string; played?: number | null; window: [number, number] | null; options?: ChipOption[]; closes?: boolean;
	best?: ChipOption; verdict?: 'play' | 'last' | 'hold' | 'later';
};

export const HORIZON: number, DECAY: number, HIT: number, MAX_FT: number;
export const CHIP_PLAY: Record<string, number>;
export function prepare(pred: PredDoc, team: TeamDoc): Prep | null;
export function lineup(ctx: Ctx, squad: number[], k: number): Lineup;
export function apply(ctx: Ctx, st: SquadState, moves: Move[]): SquadState | null;
export function bestMoves(ctx: Ctx, st: SquadState, obj: (squad: number[]) => number, quick: (p: PlanPlayer) => number,
	opts?: { singles?: number; doubles?: number; triples?: boolean }): Record<'singles' | 'doubles' | 'triples', { moves: Move[]; gain: number; state: SquadState }[]>;
export function plan(prep: Prep, opts: { ft: number; first?: Move[] | null }): Plan;
export function moveGain(prep: Prep, st: SquadState, move: Move, k: number): number | null;
export function chipAdvice(prep: Prep, planned: Plan, chips: Chip[], opts?: { locked?: boolean }): ChipAdvice[];
