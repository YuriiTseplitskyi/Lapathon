from __future__ import annotations
import re
from typing import Any, Dict, List, Tuple, Optional

# Minimal JSONPath-lite
_TOKEN_RE = re.compile(r"""
    (\$)|
    (\.\w+)|              # .key
    (\[\*\])|             # [*]
    (\[(\d+)\])           # [0]
""", re.VERBOSE)

def _parse_path(path: str) -> List[Tuple[str, Any]]:
    path = path.strip()
    if not path:
        raise ValueError("empty path")
    tokens: List[Tuple[str, Any]] = []
    pos = 0
    for m in _TOKEN_RE.finditer(path):
        if m.start() != pos:
            chunk = path[pos:m.start()].strip()
            if chunk:
                for part in chunk.split("."):
                    if part:
                        tokens.append(("key", part))
        pos = m.end()
        if m.group(1):  # $
            tokens.append(("root", None))
        elif m.group(2):  # .key
            tokens.append(("key", m.group(2)[1:]))
        elif m.group(3):  # [*]
            tokens.append(("wild", None))
        elif m.group(4):  # [n]
            tokens.append(("idx", int(m.group(5))))
    if pos < len(path):
        tail = path[pos:].strip()
        if tail:
            for part in tail.split("."):
                if part:
                    tokens.append(("key", part))
    return tokens

def jp_values(obj: Any, path: str) -> List[Any]:
    tokens = _parse_path(path)
    if tokens and tokens[0][0] == "root":
        cur = [obj]
        tokens = tokens[1:]
    else:
        cur = [obj]
    for t, v in tokens:
        nxt: List[Any] = []
        if t == "key":
            for item in cur:
                if isinstance(item, dict) and v in item:
                    nxt.append(item[v])
        elif t == "idx":
            for item in cur:
                if isinstance(item, list) and 0 <= v < len(item):
                    nxt.append(item[v])
        elif t == "wild":
            for item in cur:
                if isinstance(item, list):
                    nxt.extend(item)
                elif item is not None:
                    # Robustness for XML-to-JSON: treat singleton as list of 1
                    nxt.append(item)
        else:
            raise ValueError(f"unsupported token: {t}")
        cur = nxt
        if not cur:
            break
    out: List[Any] = []
    for x in cur:
        if x is None:
            continue
        out.append(x)
    return out

def jp_first(obj: Any, path: str) -> Optional[Any]:
    vals = jp_values(obj, path)
    return vals[0] if vals else None

def jp_exists(obj: Any, path: str) -> bool:
    return jp_first(obj, path) is not None

def eval_predicate(doc: Dict[str, Any], pred: Dict[str, Any]) ->(Tuple)[bool, int, List[str]]:
    """
    Evaluates a MatchPredicate against a document.
    pred format: {"all": [{type: "json_exists", path: "..."}], "none": [...]}
    """
    score = 0
    reasons: List[str] = []
    
    # Handle "all" predicates
    all_predicates = pred.get("all", [])
    for rule in all_predicates:
        rule_type = rule.get("type")
        path = rule.get("path")
        
        if not rule_type or not path:
            reasons.append("bad_rule_missing_type_or_path")
            continue
            
        val = jp_first(doc, path)
        ok = False
        
        if rule_type == "json_exists":
            ok = val is not None
        elif rule_type == "json_equals":
            ok = val == rule.get("value")
        elif rule_type == "json_in":
            ok = val in (rule.get("values") or [])
        elif rule_type == "json_regex":
            pat = rule.get("pattern") or ""
            ok = isinstance(val, str) and re.search(pat, val) is not None
        else:
            reasons.append(f"unsupported_type:{rule_type}")
            continue
            
        if ok:
            score += 1
        else:
            reasons.append(f"failed_{rule_type}:{path}")
            return False, score, reasons  # Early exit on "all" failure
    
    # Handle "none" predicates (must NOT match)
    none_predicates = pred.get("none", [])
    for rule in none_predicates:
        rule_type = rule.get("type")
        path = rule.get("path")
        
        if not rule_type or not path:
            continue
            
        val = jp_first(doc, path)
        should_not_exist = False
        
        if rule_type == "json_exists":
            should_not_exist = (val is not None)
        elif rule_type == "json_equals":
            should_not_exist = (val == rule.get("value"))
        
        if should_not_exist:
            reasons.append(f"none_failed_{rule_type}:{path}")
            return False, score, reasons
    
    # All "all" matched, and no "none" matched
    matched = (len(all_predicates) == 0 or score == len(all_predicates))
    return matched, score, reasons
