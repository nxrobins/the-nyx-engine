/** Vestibule types — Title Screen + Incarnation flow */

export type VestibulePhase = 'title' | 'incarnation' | 'playing';

export interface PastThread {
	thread_id: number;
	epitaph: string | null;
	hamartia: string;
	final_turn: number;
	soul_vectors: { metis: number; bia: number; kleos: number; aidos: number } | null;
}
