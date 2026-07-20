"""client_safe_state must not ship the answer key (audit V2-H3).

An armed vignette's choices each carry a ConsequencePacket — the exact vector /
pressure / bond deltas and the future seal line. Shipping pending_vignette whole
lets a player read every button's precise consequences (and the seal) before
choosing: the min-max dashboard the anti-goals forbid. The button LABELS travel
via ui_choices; the packets must never reach the wire.
"""

from __future__ import annotations

from app.schemas.state import CanonNPC, SceneState, ThreadState, WorldCanon
from app.schemas.vignette import BoundVignette, ConsequencePacket, VignetteChoice
from app.services.canon import client_safe_state


def _armed_state() -> ThreadState:
    s = ThreadState()
    s.pending_vignette = BoundVignette(
        vignette_id="weigh",
        situation="The scale reads light again.",
        choices=[
            VignetteChoice(label="Demand a true weigh", packet=ConsequencePacket(
                vector_deltas={"bia": 0.8}, pressure_deltas={"faction_heat": 0.4},
                scene_evolution="The scale is watched now.",
            )),
            VignetteChoice(label="Mark your carts", packet=ConsequencePacket(
                vector_deltas={"metis": 0.8}, scene_evolution="A quiet ledger grows.",
            )),
            VignetteChoice(label="Keep your head down", packet=ConsequencePacket(
                vector_deltas={"aidos": 0.6}, scene_evolution="You fade into the crew.",
            )),
        ],
    )
    return s


def test_pending_vignette_is_stripped_from_the_wire():
    safe = client_safe_state(_armed_state())
    assert safe.pending_vignette is None      # no packets, no seal spoiler


def test_the_real_state_keeps_the_pending_vignette():
    s = _armed_state()
    client_safe_state(s)
    assert s.pending_vignette is not None      # server truth untouched (resume needs it)
    assert s.pending_vignette.choices[0].packet.vector_deltas == {"bia": 0.8}


def test_latent_strip_still_works_alongside_pending():
    s = _armed_state()
    s.canon = WorldCanon(
        npcs={
            "npc_a": CanonNPC(npc_id="npc_a", name="Sera", role="mother",
                              home_location_id="h", current_location_id="h", status="alive"),
            "npc_l": CanonNPC(npc_id="npc_l", name="Ghost", role="stranger",
                              home_location_id="h", current_location_id="h", status="latent"),
        },
        current_scene=SceneState(scene_id="s", location_id="h"),
    )
    safe = client_safe_state(s)
    assert safe.pending_vignette is None
    assert "npc_l" not in safe.canon.npcs          # latent still stripped
    assert "npc_a" in safe.canon.npcs
    # real state intact
    assert "npc_l" in s.canon.npcs and s.pending_vignette is not None


def test_unarmed_state_with_no_latent_is_returned_unchanged():
    s = ThreadState()
    assert client_safe_state(s) is s               # fast path preserved
