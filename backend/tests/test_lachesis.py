"""Tests for Lachesis agent v2.1 — JSON parsers, mock evaluator, parse response.

Covers: _clean_json, _regex_extract, _clamp_deltas, _infer_deltas_from_action,
_mock_evaluate, _parse_response.

Oath detection and hamartia assignment tests live in test_oath_engine.py
and test_hamartia_engine.py respectively (P1-002 split).
"""

from app.agents.lachesis import (
    _clean_json,
    _clamp_deltas,
    _infer_deltas_from_action,
    _mock_evaluate,
    _parse_response,
    _regex_extract,
)
from app.schemas.state import SoulVectors, ThreadState


# ---------------------------------------------------------------------------
# _clean_json
# ---------------------------------------------------------------------------

class TestCleanJson:
    def test_strips_markdown_fences(self):
        raw = '```json\n{"valid_action": true}\n```'
        assert '"valid_action": true' in _clean_json(raw)

    def test_extracts_json_object(self):
        raw = 'Here is the result: {"valid_action": true, "reason": ""} end.'
        cleaned = _clean_json(raw)
        assert cleaned.startswith("{")
        assert cleaned.endswith("}")

    def test_removes_trailing_commas(self):
        raw = '{"valid_action": true, "reason": "test",}'
        cleaned = _clean_json(raw)
        assert ",}" not in cleaned

    def test_already_clean_json(self):
        raw = '{"valid_action": true, "reason": ""}'
        assert _clean_json(raw) == raw

    def test_empty_string(self):
        assert _clean_json("") == ""

    def test_no_json_object(self):
        raw = "This has no JSON at all."
        # Should return whatever it can
        cleaned = _clean_json(raw)
        assert isinstance(cleaned, str)


# ---------------------------------------------------------------------------
# _regex_extract
# ---------------------------------------------------------------------------

class TestRegexExtract:
    def test_extracts_valid_action(self):
        raw = '{"valid_action": false, "reason": "impossible"}'
        data = _regex_extract(raw)
        assert data["valid_action"] is False
        assert data["reason"] == "impossible"

    def test_extracts_vector_deltas(self):
        raw = '{"vector_deltas": {"metis": 2.0, "bia": -1.5, "kleos": 0.5}}'
        data = _regex_extract(raw)
        assert data["vector_deltas"]["metis"] == 2.0
        assert data["vector_deltas"]["bia"] == -1.5

    def test_extracts_oath_detected(self):
        raw = '{"oath_detected": "I swear to protect the child"}'
        data = _regex_extract(raw)
        assert data["oath_detected"] == "I swear to protect the child"

    def test_extracts_assigned_hamartia(self):
        raw = '{"assigned_hamartia": "Hubris"}'
        data = _regex_extract(raw)
        assert data["assigned_hamartia"] == "Hubris"

    def test_defaults_when_missing(self):
        raw = "{}"
        data = _regex_extract(raw)
        assert data["valid_action"] is True  # default
        assert data["reason"] == ""
        assert data["vector_deltas"] == {}
        assert data["oath_detected"] is None
        assert data["assigned_hamartia"] is None

    def test_extracts_environment_update(self):
        raw = '{"environment_update": "A dark cave entrance."}'
        data = _regex_extract(raw)
        assert data["environment_update"] == "A dark cave entrance."


# ---------------------------------------------------------------------------
# _clamp_deltas
# ---------------------------------------------------------------------------

class TestClampDeltas:
    def test_within_range(self):
        assert _clamp_deltas({"bia": 2.0, "metis": -1.0}) == {"bia": 2.0, "metis": -1.0}

    def test_clamp_upper(self):
        assert _clamp_deltas({"bia": 5.0})["bia"] == 3.0

    def test_clamp_lower(self):
        assert _clamp_deltas({"metis": -5.0})["metis"] == -2.0

    def test_filters_invalid_keys(self):
        result = _clamp_deltas({"bia": 1.0, "hubris": 5.0})
        assert "hubris" not in result
        assert "bia" in result

    def test_empty_deltas(self):
        assert _clamp_deltas({}) == {}


# ---------------------------------------------------------------------------
# _infer_deltas_from_action
# ---------------------------------------------------------------------------

class TestInferDeltas:
    def test_combat_keywords(self):
        result = _infer_deltas_from_action("I attack the guard")
        assert result.get("bia", 0) > 0

    def test_deception_keywords(self):
        result = _infer_deltas_from_action("I deceive the merchant")
        assert result.get("metis", 0) > 0

    def test_glory_keywords(self):
        result = _infer_deltas_from_action("I boast of my victory")
        assert result.get("kleos", 0) > 0

    def test_stealth_keywords(self):
        result = _infer_deltas_from_action("I hide in the shadows")
        assert result.get("aidos", 0) > 0

    def test_neutral_fallback(self):
        result = _infer_deltas_from_action("I look around")
        # neutral fallback
        assert "metis" in result or "aidos" in result


# ---------------------------------------------------------------------------
# _mock_evaluate
# ---------------------------------------------------------------------------

class TestMockEvaluate:
    def test_combat_action(self, mid_game_state: ThreadState):
        result = _mock_evaluate(mid_game_state, "attack the beast")
        assert result.valid_action is True
        assert result.vector_deltas.get("bia", 0) > 0

    def test_deception_action(self, mid_game_state: ThreadState):
        result = _mock_evaluate(mid_game_state, "deceive the guard")
        assert result.valid_action is True
        assert result.vector_deltas.get("metis", 0) > 0

    def test_glory_action(self, mid_game_state: ThreadState):
        result = _mock_evaluate(mid_game_state, "boast of my conquests")
        assert result.valid_action is True
        assert result.vector_deltas.get("kleos", 0) > 0

    def test_stealth_action(self, mid_game_state: ThreadState):
        result = _mock_evaluate(mid_game_state, "hide behind the pillar")
        assert result.valid_action is True
        assert result.vector_deltas.get("aidos", 0) > 0

    def test_invalid_action(self, mid_game_state: ThreadState):
        result = _mock_evaluate(mid_game_state, "I fly into the sky")
        assert result.valid_action is False
        assert "mortal" in result.reason.lower()

    def test_neutral_action(self, mid_game_state: ThreadState):
        result = _mock_evaluate(mid_game_state, "I look around the room")
        assert result.valid_action is True
        # Neutral gives small metis + aidos
        assert "metis" in result.vector_deltas or "aidos" in result.vector_deltas

    def test_no_oath_in_mock(self, mid_game_state: ThreadState):
        """Lachesis mock no longer detects oaths — kernel handles it."""
        result = _mock_evaluate(mid_game_state, "I swear to avenge my father")
        assert result.oath_detected is None

    def test_updated_state_is_copy(self, mid_game_state: ThreadState):
        result = _mock_evaluate(mid_game_state, "attack")
        # Ensure it's a deep copy, not the original
        assert result.updated_state is not mid_game_state
        assert result.updated_state.last_action == "attack"

    def test_no_hamartia_in_mock(self, unformed_turn10_state: ThreadState):
        """Lachesis mock no longer assigns hamartia — kernel handles it."""
        result = _mock_evaluate(unformed_turn10_state, "look around")
        assert result.assigned_hamartia is None


# ---------------------------------------------------------------------------
# _parse_response (full JSON → LachesisResponse)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_json_response(self, mid_game_state: ThreadState):
        raw = '''{
            "valid_action": true,
            "reason": "",
            "vector_deltas": {"bia": 2.0, "aidos": -0.5},
            "outcome_type": "violent_triumph",
            "oath_detected": null,
            "oath_violation": null,
            "environment_update": "Blood stains the cobblestones.",
            "rag_summary": "Player attacked the merchant violently."
        }'''
        result = _parse_response(raw, mid_game_state, "attack")
        assert result.valid_action is True
        assert result.vector_deltas["bia"] == 2.0
        assert result.environment_update == "Blood stains the cobblestones."

    def test_invalid_action_response(self, mid_game_state: ThreadState):
        raw = '{"valid_action": false, "reason": "You cannot fly."}'
        result = _parse_response(raw, mid_game_state, "fly away")
        assert result.valid_action is False
        assert "fly" in result.reason.lower()

    def test_markdown_wrapped_json(self, mid_game_state: ThreadState):
        raw = '```json\n{"valid_action": true, "vector_deltas": {"metis": 1.5}}\n```'
        result = _parse_response(raw, mid_game_state, "think carefully")
        assert result.valid_action is True
        assert result.vector_deltas.get("metis") == 1.5

    def test_empty_deltas_triggers_inference(self, mid_game_state: ThreadState):
        raw = '{"valid_action": true, "vector_deltas": {}}'
        result = _parse_response(raw, mid_game_state, "attack the goblin")
        # Should use keyword inference fallback
        assert result.vector_deltas.get("bia", 0) > 0

    def test_delta_clamping(self, mid_game_state: ThreadState):
        raw = '{"valid_action": true, "vector_deltas": {"bia": 10.0}}'
        result = _parse_response(raw, mid_game_state, "attack")
        assert result.vector_deltas["bia"] == 3.0  # clamped

    def test_no_oath_fallback_in_parse(self, mid_game_state: ThreadState):
        """_parse_response no longer detects oaths — kernel handles it."""
        raw = '{"valid_action": true, "vector_deltas": {"aidos": 1.0}}'
        result = _parse_response(raw, mid_game_state, "I swear to protect the child")
        assert result.oath_detected is None

    def test_hamartia_fork_via_parse(self, unformed_turn10_state: ThreadState):
        raw = '{"valid_action": true, "vector_deltas": {"metis": 1.0}, "assigned_hamartia": "Hubris"}'
        result = _parse_response(raw, unformed_turn10_state, "ponder the riddle")
        assert result.assigned_hamartia == "Hubris"

    def test_no_hamartia_fallback_in_parse(self, unformed_turn10_state: ThreadState):
        """_parse_response no longer assigns hamartia — kernel handles it."""
        raw = '{"valid_action": true, "vector_deltas": {"metis": 1.0}}'
        result = _parse_response(raw, unformed_turn10_state, "ponder the riddle")
        assert result.assigned_hamartia is None

    def test_completely_broken_json_uses_regex(self, mid_game_state: ThreadState):
        raw = 'This is not JSON at all but "valid_action": true and "vector_deltas": {"bia": 2.0}'
        result = _parse_response(raw, mid_game_state, "attack")
        # Should fall through to regex extraction
        assert result.valid_action is True

    def test_rag_context_appended(self, mid_game_state: ThreadState):
        initial_ctx_len = len(mid_game_state.rag_context)
        raw = '{"valid_action": true, "vector_deltas": {"bia": 1.0}, "rag_summary": "test entry"}'
        result = _parse_response(raw, mid_game_state, "attack")
        assert len(result.updated_state.rag_context) == initial_ctx_len + 1
