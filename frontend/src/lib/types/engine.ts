/** Frontend mirror of backend Pydantic schemas — v2.0 Soul Ledger */

export interface SoulVectors {
	metis: number;   // cunning, intellect
	bia: number;     // force, violence
	kleos: number;   // glory, fame
	aidos: number;   // shadow, restraint
}

export interface Oath {
	oath_id: string;
	text: string;
	turn_sworn: number;
	broken: boolean;
}

export interface SoulLedger {
	hamartia: string;
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

export interface ThreadState {
	session: SessionData;
	soul_ledger: SoulLedger;
	the_loom: TheLoom;
	rag_context: string[];
	world_context: string;
	last_action: string;
	last_outcome: string;
	current_dream: string; // Hypnos dream text (consumed by next Clotho call)
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
