"""Bounded expression evaluation and ownership/input contracts (offline audit 1.3.9).

No clinical dose thresholds are defined here. Invalid inputs are rejected before
an attempt, score, time, or clinical state is changed.
"""
from __future__ import annotations
import ast
import math
from copy import deepcopy
from functools import lru_cache, wraps

ENGINE_REVISION = "1.3.9-audit.3"


def assert_finite_tree(value, path="root", depth=0):
    if depth > 64:
        raise ValueError(f"Object nesting exceeds limit at {path}")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite value at {path}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Non-string key at {path}")
            assert_finite_tree(item, f"{path}.{key}", depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_finite_tree(item, f"{path}[{index}]", depth + 1)
        return
    raise ValueError(f"Unsupported value type at {path}: {type(value).__name__}")


def isolated_result(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        result = deepcopy(fn(*args, **kwargs))
        assert_finite_tree(result)
        return result
    return wrapped


_ALLOWED_NAMES = {"t", "vitals", "symptoms", "flags", "grade", "age_sbp_threshold",
                  "action_first_time", "action_valid_time", "min", "max", "int", "float", "bool"}
_BUILTINS = {"min": min, "max": max, "int": int, "float": float, "bool": bool}
_ALLOWED_NODES = (ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Name, ast.Load, ast.Constant, ast.Attribute, ast.Subscript, ast.Call,
    ast.List, ast.Tuple, ast.Set, ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Eq, ast.NotEq,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)


@lru_cache(maxsize=512)
def compile_condition(expr):
    if not isinstance(expr, str) or len(expr) > 4096:
        raise ValueError("Invalid or oversized condition")
    tree = ast.parse(expr, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > 256:
        raise ValueError("Condition is too complex")
    for node in nodes:
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"Forbidden expression node: {type(node).__name__}")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and len(node.value) > 128:
                raise ValueError("Oversized literal")
            if isinstance(node.value, (int, float)) and (not math.isfinite(node.value) or abs(node.value) > 1e9):
                raise ValueError("Oversized numeric literal")
        if isinstance(node, ast.BinOp):
            # No sequence multiplication/formatting or arbitrary flag arithmetic.
            # Registered arithmetic only uses numbers, simulation time, and vital/symptom values.
            for operand in ast.walk(node):
                if isinstance(operand, (ast.List, ast.Tuple, ast.Set, ast.Call, ast.Subscript)):
                    raise ValueError("Only scalar arithmetic is allowed")
                if isinstance(operand, ast.Constant) and not isinstance(operand.value, (int, float)):
                    raise ValueError("Only numeric arithmetic is allowed")
                if (isinstance(operand, ast.Attribute) and operand.value.id not in {"vitals", "symptoms"}
                        and not (operand.value.id == "flags" and operand.attr == "bp_ordered_at_sec")):
                    raise ValueError("Unsafe nonnumeric attribute arithmetic")
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_NAMES:
            raise ValueError("Forbidden expression name")
        if isinstance(node, ast.Attribute):
            root = node.value
            if (node.attr.startswith("_") or not isinstance(root, ast.Name)
                    or root.id not in {"flags", "vitals", "symptoms", "action_first_time", "action_valid_time"}):
                raise ValueError("Forbidden attribute access")
            if root.id.startswith("action_") and node.attr != "get":
                raise ValueError("Only read-only timeline lookup is allowed")
        if isinstance(node, ast.Call):
            allowed = isinstance(node.func, ast.Name) and node.func.id in _BUILTINS
            allowed_get = (isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"action_first_time", "action_valid_time"})
            if not (allowed or allowed_get) or node.keywords:
                raise ValueError("Forbidden call")
    return compile(tree, "<scenario-condition>", "eval")


def safe_eval(expr, ctx):
    if not expr:
        return False
    bp_time = getattr(ctx.get("flags"), "bp_ordered_at_sec", None)
    if bp_time is not None and (isinstance(bp_time, bool) or not isinstance(bp_time, (int, float))):
        raise ValueError("Nonnumeric measurement timestamp")
    local = dict(_BUILTINS)
    local.update(ctx)
    return bool(eval(compile_condition(expr), {"__builtins__": {}}, local))


def numeric_command(completion_flag, argument_name):
    """Validate a numerical command atomically, and prevent accidental redosing."""
    def decorate(fn):
        @wraps(fn)
        def wrapped(self, value=None, *args, **kwargs):
            if value is None and argument_name in kwargs:
                value = kwargs.pop(argument_name)
            try:
                if isinstance(value, bool):
                    raise ValueError("Boolean is not a dose")
                parsed = float(value)
                if not math.isfinite(parsed) or parsed < 0:
                    raise ValueError("Dose must be finite and non-negative")
            except (ValueError, TypeError, OverflowError):
                return {"status": "invalid_input", "accepted": False,
                        "message": "请输入有限、非负的有效数值；本次未执行、未计时、未计分。"}
            if self.is_done()[0]:
                return {"status": "terminal", "accepted": False, "message": "本轮已结束，请开始新一轮。"}
            action_id = kwargs.get("action_id", args[0] if args else "im_epinephrine")
            if fn.__name__ == "apply_epinephrine_dose" and action_id not in ("im_epinephrine", "repeat_epinephrine"):
                return {"status": "invalid_input", "accepted": False, "message": "无效的肾上腺素操作编号。"}
            repeat = fn.__name__ == "apply_epinephrine_dose" and action_id == "repeat_epinephrine"
            if not repeat and self.state.flags.get(completion_flag, False):
                return {"status": "already_completed", "accepted": False, "message": "该次治疗已经有效完成，不重复给药。"}
            if fn.__name__ == "apply_steroid_dose" and not self.state.flags.get("iv_access", True):
                return {"status": "no_iv_access", "accepted": False, "message": "静脉通路不可用，不能完成静脉给药。"}
            result = fn(self, parsed, *args, **kwargs)
            if fn.__name__ in ("apply_fluid_bolus_volume", "apply_steroid_dose") and result.get("status") in (
                    "under", "over", "invalid", "timing_error", "used_before_first_line", "no_iv_access"):
                aid = "fluid_bolus" if fn.__name__ == "apply_fluid_bolus_volume" else "steroid"
                self._record_order_violation(aid, "此前存在不符合时机、通路或剂量要求的实际尝试；纠正后不追溯为首次正确满分。")
            result["accepted"] = result.get("status") not in ("error", "invalid_input", "already_completed", "terminal")
            assert_finite_tree(result)
            return result
        return wrapped
    return decorate
