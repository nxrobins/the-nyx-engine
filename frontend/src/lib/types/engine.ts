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
	first_memory: string;
	turn_count: number;
	run_number: number;
	current_environment: string;
	epoch_phase: number;   // 1-4
	ui_mode: string;       // "buttons" | "open"
}

export interface ThreadState {
	session: SessionData;
	soul_ledger: SoulLedger;
	the_loom: TheLoom;
	rag_context: string[];
	last_action: string;
	last_outcome: string;
}

export interface TurnResult {
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

/** Hamartia options returned by GET /hamartia-options */
export interface HamartiaOptions {
	options: string[];
}
