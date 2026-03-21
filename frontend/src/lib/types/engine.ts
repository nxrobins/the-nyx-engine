/** Frontend mirror of backend Pydantic schemas — v2.0 Soul Ledger */

export interface SoulVectors {
	metis: number;   // cunning, intellect
	bia: number;     // force, violence
	kleos: number;   // glory, fame
	aidos: number;   // shadow, restraint
}

export interface OathTerms {
	subject: string;
	promised_action: string;
	protected_target: string | null;
	forbidden_action: string | null;
	deadline: string | null;
	witness: string | null;
	price: string | null;
}

export interface Oath {
	oath_id: string;
	text: string;
	turn_sworn: number;
	broken: boolean;
	terms: OathTerms | null;
	status: string;
	fulfillment_note: string;
}

export interface HamartiaProfile {
	name: string;
	choice_bias: string;
	nemesis_multiplier: number;
	eris_bias: number;
	style_directive: string;
	refusal_pattern: string;
	social_cost_bias: string;
}

export interface SoulLedger {
	hamartia: string;
	hamartia_profile: HamartiaProfile | null;
	vectors: SoulVectors;
	active_oaths: Oath[];
}

export interface TheLoom {
	current_prophecy: string;
	milestone_reached: boolean;
	image_prompt_trigger: string;
}

export interface SessionData {
	player_id: string;
	player_name: string;
	player_gender: string;
	hamartia: string;
	first_memory: string;
	turn_count: number;
	run_number: number;
	current_environment: string;
	epoch_phase: number;   // 1-4
	ui_mode: string;       // "buttons" | "open"
	player_age: number;    // deterministic age per turn
	beat_position: string; // SETUP | COMPLICATION | RESOLUTION | OPEN
}

export interface CanonNPC {
	npc_id: string;
	name: string;
	role: string;
	home_location_id: string;
	current_location_id: string;
	status: string;
	trust: number;
	fear: number;
	obligation: number;
	tags: string[];
	last_seen_turn: number;
}

export interface CanonLocation {
	location_id: string;
	name: string;
	region: string;
	kind: string;
	current_condition: string;
	tags: string[];
}

export interface CanonFaction {
	faction_id: string;
	name: string;
	stance: string;
	leverage: number;
	hostility: number;
	notes: string;
}

export interface SceneClock {
	clock_id: string;
	label: string;
	progress: number;
	max_segments: number;
	stakes: string;
	resolution_hint: string;
}

export interface SceneState {
	scene_id: string;
	location_id: string;
	present_npc_ids: string[];
	active_clock_ids: string[];
	immediate_problem: string;
	scene_objective: string;
	carryover_consequence: string;
}

export interface WorldCanon {
	npcs: Record<string, CanonNPC>;
	locations: Record<string, CanonLocation>;
	factions: Record<string, CanonFaction>;
	clocks: Record<string, SceneClock>;
	current_scene: SceneState | null;
	world_facts: string[];
}

export interface AgentProposal {
	agent: string;
	allow_action: boolean;
	refusal_reason: string;
	scene_patch: Record<string, unknown>;
	vector_patch: Record<string, number>;
	pressure_patch: Record<string, number>;
	prophecy_patch: string;
	death_flag: boolean;
	death_reason: string;
	intervention_copy: string;
	priority_note: string;
	confidence: number;
}

export interface DeliberationTrace {
	turn_number: number;
	proposals: AgentProposal[];
	winner_order: string[];
	final_reason: string;
}

export interface SceneOutcome {
	material_changes: string[];
	present_npcs: string[];
	immediate_problem: string;
	intervening_fates: string[];
	must_not_contradict: string[];
	pressure_changes: Record<string, number>;
	pressure_summary: string;
}

export interface PressureState {
	suspicion: number;
	scarcity: number;
	wounds: number;
	debt: number;
	faction_heat: number;
	omen: number;
	exploit_score: number;
	stability_streak: number;
}

export interface LegacyEcho {
	source_thread_id: string;
	epitaph: string;
	hamartia: string;
	inherited_mark: string;
	mechanical_effect: string;
}

export interface ThreadState {
	session: SessionData;
	soul_ledger: SoulLedger;
	the_loom: TheLoom;
	pressures: PressureState;
	canon: WorldCanon | null;
	rag_context: string[];
	world_context: string;
	last_action: string;
	last_outcome: string;
	current_dream: string; // Hypnos dream text (consumed by next Clotho call)
	recent_traces: DeliberationTrace[];
	legacy_echoes: LegacyEcho[];
}

export interface TurnResult {
	session_id: string;
	prose: string;
	state: ThreadState;
	terminal: boolean;
	death_reason: string;
	nemesis_struck: boolean;
	eris_struck: boolean;
	turn_number: number;
	image_url: string;
	ui_choices: string[];
}

export interface HypnosEvent {
	text: string;
}

/** Mechanic event from the streaming pipeline (Phase 1) */
export interface MechanicEvent {
	vector_deltas: Record<string, number>;
	dominant: string;
	outcome: string;
	nemesis_struck: boolean;
	eris_struck: boolean;
	valid: boolean;
}

/** Hamartia options returned by GET /hamartia-options */
export interface HamartiaOptions {
	options: string[];
}
