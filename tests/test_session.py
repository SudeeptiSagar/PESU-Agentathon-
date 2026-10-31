"""CORE-06: the state machine table, the COMMITTING guard, stop, and pause/resume."""
import re
from pathlib import Path

import pytest

from app.session import (STATES, TRANSITIONS, IllegalTransition, Session, can_transition,
                         confirm, resume, transition)

PENDING = {"element_id": "b1", "label": "Submit application", "kind": "submit",
           "url": "http://localhost:8000/portal/apply.html", "domain": "localhost"}


def make(state, **kw):
    kw.setdefault("pending_action", dict(PENDING))
    return Session(state=state, **kw)


# ---------------------------------------------------------------- the table
def test_every_state_has_a_row_and_only_known_targets():
    assert set(TRANSITIONS) == set(STATES)
    for old, targets in TRANSITIONS.items():
        assert targets <= set(STATES) and old not in targets


LEGAL = [(a, b) for a in STATES for b in TRANSITIONS[a]]
ILLEGAL = [(a, b) for a in STATES for b in STATES
           if a != b and b != "IDLE" and b not in TRANSITIONS[a]
           and a not in ("PAUSED", "NEEDS_HUMAN_CHECK")]


@pytest.mark.parametrize("old,new", LEGAL)
def test_legal_transition_succeeds(old, new):
    s = make(old, confirmed=(new == "COMMITTING"))
    transition(s, new)
    assert s.state == new


@pytest.mark.parametrize("old,new", ILLEGAL)
def test_illegal_transition_raises_and_leaves_state_alone(old, new):
    s = make(old, confirmed=True)
    with pytest.raises(IllegalTransition):
        transition(s, new)
    assert s.state == old and not can_transition(s, new)


def test_unknown_state_raises():
    with pytest.raises(IllegalTransition):
        transition(make("ACTING"), "FLYING")
    with pytest.raises(IllegalTransition):
        transition(make("NOT_A_STATE"), "ACTING")


def test_same_state_is_a_no_op():
    s = make("AWAITING_CONFIRM", confirmed=True)
    transition(s, "AWAITING_CONFIRM")
    assert s.state == "AWAITING_CONFIRM" and s.confirmed  # not reset by a no-op


def test_a_normal_form_task_walks_the_whole_path():
    s = Session()
    for step in ("PLANNING", "ACTING"):
        transition(s, step)
    s.pending_action = dict(PENDING)
    for step in ("VERIFYING", "READBACK", "AWAITING_CONFIRM"):
        transition(s, step)
    confirm(s)
    assert s.state == "COMMITTING"
    transition(s, "DONE")
    transition(s, "IDLE")
    assert s.state == "IDLE"


# ---------------------------------------------------------------- COMMITTING guard (hard rule 2)
@pytest.mark.parametrize("state", [x for x in STATES if x not in ("AWAITING_CONFIRM", "COMMITTING")])
def test_committing_unreachable_from_any_other_state(state):
    s = make(state, confirmed=True, saved_state="AWAITING_CONFIRM")
    with pytest.raises(IllegalTransition):
        transition(s, "COMMITTING")


def test_committing_needs_confirmed_and_a_pending_action():
    with pytest.raises(IllegalTransition):
        transition(make("AWAITING_CONFIRM", confirmed=False), "COMMITTING")
    with pytest.raises(IllegalTransition):
        transition(make("AWAITING_CONFIRM", confirmed=True, pending_action=None), "COMMITTING")
    ok = make("AWAITING_CONFIRM", confirmed=True)
    transition(ok, "COMMITTING")
    assert ok.state == "COMMITTING"


def test_confirmation_is_single_use():
    s = make("COMMITTING", confirmed=True)
    transition(s, "DONE")
    assert s.confirmed is False and s.pending_action is None


def test_a_stale_confirmation_cannot_be_reused():
    s = make("AWAITING_CONFIRM", confirmed=True)
    transition(s, "ACTING")              # user said "change the PIN code" instead
    assert s.confirmed is False
    transition(s, "AWAITING_CONFIRM")    # a new question is asked
    assert s.confirmed is False
    with pytest.raises(IllegalTransition):
        transition(s, "COMMITTING")


def test_confirm_helper_only_works_while_awaiting_confirm():
    for state in STATES:
        if state == "AWAITING_CONFIRM":
            continue
        s = make(state)
        with pytest.raises(IllegalTransition):
            confirm(s)
        assert s.confirmed is False and s.state == state


def test_confirm_helper_commits_and_a_failed_confirm_leaves_nothing_set():
    s = make("AWAITING_CONFIRM")
    confirm(s)
    assert s.state == "COMMITTING" and s.confirmed
    broken = make("AWAITING_CONFIRM", pending_action=None)  # should not happen, but be safe
    with pytest.raises(IllegalTransition):
        confirm(broken)
    assert broken.confirmed is False and broken.state == "AWAITING_CONFIRM"


def test_confirm_while_paused_does_nothing():
    s = make("AWAITING_CONFIRM")
    transition(s, "PAUSED")
    with pytest.raises(IllegalTransition):
        confirm(s)
    assert s.state == "PAUSED" and not s.confirmed


def test_verifying_readback_and_confirm_need_something_to_confirm():
    for new in ("VERIFYING", "READBACK", "AWAITING_CONFIRM"):
        origin = {"VERIFYING": "ACTING", "READBACK": "VERIFYING", "AWAITING_CONFIRM": "READBACK"}[new]
        with pytest.raises(IllegalTransition):
            transition(make(origin, pending_action=None), new)


# ---------------------------------------------------------------- stop (hard rule 7)
@pytest.mark.parametrize("state", STATES)
def test_stop_always_works_and_drops_everything(state):
    s = make(state, confirmed=True, saved_state="ACTING", failures=2)
    transition(s, "IDLE")
    assert (s.state, s.confirmed, s.pending_action, s.saved_state, s.failures) == \
        ("IDLE", False, None, None, 0)


# ---------------------------------------------------------------- pause / human check
@pytest.mark.parametrize("pause_state", ["PAUSED", "NEEDS_HUMAN_CHECK"])
def test_pause_and_human_check_save_and_restore_state(pause_state):
    s = make("ACTING")
    transition(s, pause_state)
    assert s.state == pause_state and s.saved_state == "ACTING"
    assert resume(s) == "ACTING"
    assert s.state == "ACTING" and s.saved_state is None


@pytest.mark.parametrize("pause_state", ["PAUSED", "NEEDS_HUMAN_CHECK"])
def test_paused_can_only_resume_where_it_came_from_or_stop(pause_state):
    s = make("ACTING")
    transition(s, pause_state)
    for other in STATES:
        if other in (pause_state, "ACTING", "IDLE"):
            continue
        with pytest.raises(IllegalTransition):
            transition(s, other)
    transition(s, "IDLE")


def test_resume_outside_pause_raises():
    with pytest.raises(IllegalTransition):
        resume(make("ACTING"))


def test_pause_during_confirmation_keeps_the_action_but_not_the_confirmation():
    s = make("AWAITING_CONFIRM", confirmed=True)
    transition(s, "PAUSED")
    assert s.pending_action == PENDING and s.confirmed is False
    assert resume(s) == "AWAITING_CONFIRM"
    assert s.confirmed is False
    with pytest.raises(IllegalTransition):
        transition(s, "COMMITTING")        # must say "confirm" again


@pytest.mark.parametrize("state", ["IDLE", "DONE", "NEEDS_USER", "NEEDS_HUMAN_CHECK", "COMMITTING"])
def test_cannot_pause_from_these_states(state):
    with pytest.raises(IllegalTransition):
        transition(make(state), "PAUSED")


@pytest.mark.parametrize("state", ["VERIFYING", "READBACK", "AWAITING_CONFIRM", "IDLE", "DONE",
                                   "NEEDS_USER", "PAUSED", "COMMITTING"])
def test_human_check_only_from_planning_or_acting(state):
    with pytest.raises(IllegalTransition):
        transition(make(state), "NEEDS_HUMAN_CHECK")


def test_commit_cannot_be_interrupted_into_a_resumable_state():
    s = make("COMMITTING", confirmed=True)
    for new in ("PAUSED", "NEEDS_HUMAN_CHECK"):
        with pytest.raises(IllegalTransition):
            transition(s, new)


# ---------------------------------------------------------------- nobody bypasses the machine
APP = Path(__file__).resolve().parent.parent / "app"
OTHER_MODULES = [p for p in APP.glob("*.py") if p.name != "session.py"]


@pytest.mark.parametrize("path", OTHER_MODULES, ids=lambda p: p.name)
def test_only_session_py_assigns_state_or_sets_confirmed_true(path):
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"\.state\s*=[^=]", text), f"{path.name} assigns .state; use transition()"
    assert not re.search(r"\.confirmed\s*=\s*True", text), \
        f"{path.name} sets confirmed=True; only session.confirm() may"
