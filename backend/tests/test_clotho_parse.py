"""_parse_clotho_output — the non-streaming choice parser.

The malformed-choices-tail path used to return raw.strip() (with the
---CHOICES--- marker + raw JSON still embedded) as player prose, which was then
shown to the player and persisted. These pin that the marker never leaks,
however the choices tail is malformed, while valid choices still parse.
"""

from __future__ import annotations

from app.agents.clotho import _parse_clotho_output

_PROSE = "You wait by the cold door, counting the boots in the hall."


class TestParseClothoOutput:
    def test_valid_choices_parsed_prose_marker_free(self):
        prose, choices = _parse_clotho_output(
            f'{_PROSE}\n\n---CHOICES---\n["Stay", "Leave"]', 2
        )
        assert prose == _PROSE
        assert choices == ["Stay", "Leave"]

    def test_trailing_comma_tail_falls_back_without_leaking_marker(self):
        prose, choices = _parse_clotho_output(
            f'{_PROSE}\n\n---CHOICES---\n["Stay", "Leave",]', 2
        )
        assert "---CHOICES---" not in prose
        assert prose == _PROSE
        assert choices and all(isinstance(c, str) for c in choices)  # deterministic fallback

    def test_dict_instead_of_list_falls_back_without_leaking_marker(self):
        prose, choices = _parse_clotho_output(
            f'{_PROSE}\n\n---CHOICES---\n{{"a": 1}}', 2
        )
        assert "---CHOICES---" not in prose
        assert prose == _PROSE
        assert choices  # fallback

    def test_non_string_choice_item_falls_back_without_leaking_marker(self):
        prose, choices = _parse_clotho_output(
            f'{_PROSE}\n\n---CHOICES---\n["Stay", 3]', 2
        )
        assert "---CHOICES---" not in prose
        assert prose == _PROSE
        assert choices  # fallback

    def test_no_separator_returns_whole_output_as_prose(self):
        prose, choices = _parse_clotho_output(_PROSE, 2)
        assert prose == _PROSE
        assert choices  # fallback choices

    def test_phase_four_returns_empty_choices(self):
        _, choices = _parse_clotho_output(_PROSE, 4)
        assert choices == []
