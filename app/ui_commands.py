"""UI-independent command boundary used by Streamlit callbacks.

Callbacks mutate state BEFORE a full render. Timers never mutate a Simulator.
An event is scoped to its run/session and observed revision; stale work is dropped.
"""
from __future__ import annotations
from typing import Any, MutableMapping
from academy_interactions import apply_academy_action

PENDING_FIELDS = {"epinephrine": "pending_dose", "fluid": "pending_volume", "steroid": "pending_steroid"}


def revision(sim):
    return (int(sim.state.t), len(sim.log))


def pending_input(state):
    return any(state.get(prefix + "_action_id") for prefix in PENDING_FIELDS.values())


def execute_command(state: MutableMapping[str, Any], session_id: str, expected_revision,
                    command: str, action_id: str = "", value=None):
    sim = state.get("active_simulator")
    rejected = lambda status, msg: {"accepted": False, "status": status, "message": msg, "tick_advanced": False}
    if sim is None or str(state.get("session_id", "")) != str(session_id):
        return rejected("stale_event", "旧会话操作已丢弃。")
    if revision(sim) != tuple(expected_revision):
        return rejected("stale_event", "页面状态已更新，旧操作已丢弃。")
    if command == "cancel":
        for prefix in PENDING_FIELDS.values():
            state[prefix + "_action_id"] = ""
            state[prefix + "_action_label"] = ""
        return rejected("cancelled", "已取消输入，未执行治疗。")
    if sim.is_done()[0] or state.get("ended", False):
        return rejected("terminal", "本轮已结束。")
    if command in ("action", "advance_time") and pending_input(state):
        return rejected("input_pending", "请先确认或取消当前剂量输入。")
    if command == "action" and action_id in ("im_epinephrine", "repeat_epinephrine", "fluid_bolus", "steroid"):
        # Preserve the immediate-CPR branch: a pending panel must not hide an action after arrest.
        if not (sim.state.flags.get("cardiac_arrest") and not sim.state.flags.get("cpr_done")):
            kind = "epinephrine" if action_id in ("im_epinephrine", "repeat_epinephrine") else ("fluid" if action_id == "fluid_bolus" else "steroid")
            prefix = PENDING_FIELDS[kind]
            state[prefix + "_action_id"] = action_id
            state[prefix + "_action_label"] = action_id
            return rejected("input_required", "请确认本次剂量或容量。")
    if command in PENDING_FIELDS:
        prefix = PENDING_FIELDS[command]
        if state.get(prefix + "_action_id") != action_id:
            return rejected("stale_event", "输入面板已经关闭或更换。")
        if command == "epinephrine":result = sim.apply_epinephrine_dose(value, action_id=action_id)
        elif command == "fluid":result = sim.apply_fluid_bolus_volume(value)
        else:result = sim.apply_steroid_dose(value)
        if not result.get("accepted", False):
            return {**result, "tick_advanced": False}
        state[prefix + "_action_id"] = ""
        state[prefix + "_action_label"] = ""
    elif command == "action":
        before = len(sim.log)
        if sim._is_academy_basic_case():
            r = apply_academy_action(sim, action_id)
            result = {"accepted": r["executed"], "status": "action", "message": r["feedback"]}
        else:
            sim.apply_action(action_id)
            entries = [e for e in sim.log[before:] if e.kind == "action"]
            latest = entries[-1] if entries else None
            status = latest.data.get("status", "action") if latest else "terminal"
            if latest and latest.message == "unknown_action":status = "unknown_action"
            result = {"accepted": latest is not None and status not in ("already_completed", "terminal", "unknown_action"),
                      "status": status, "message": latest.data.get("result", "") if latest else ""}
        if not result["accepted"]:return {**result, "tick_advanced": False}
    elif command == "advance_time":
        result = {"accepted": True, "status": "time_advanced", "message": ""}
    else:
        return rejected("invalid_command", "无效操作。")
    old_time = sim.state.t
    sim.tick()
    return {**result, "tick_advanced": sim.state.t != old_time}
