import re
from typing import Any, Dict, Optional, List

def apply_transformation(value: Any, transform_def: Dict[str, Any]) -> Any:
    """
    Applies a transformation to a value based on a dictionary definition.
    
    Supported types:
    - regex: Extract a group from a string pattern.
    - split: Split string by delimiter and take index.
    - map: Map specific input values to output values (exact match).
    - clean: Standard cleanup (trim, collapse spaces).
    """
    if value is None:
        return None
        
    t_type = transform_def.get("type")
    
    if t_type == "regex":
        pattern = transform_def.get("pattern")
        group = transform_def.get("group", 1)
        if isinstance(value, str) and pattern:
            match = re.search(pattern, value)
            if match:
                try:
                    return match.group(group)
                except IndexError:
                    return None
            return None # No match returns None or original? Usually None if extraction fails.

    elif t_type == "split":
        delimiter = transform_def.get("delimiter", ",")
        index = transform_def.get("index", 0)
        if isinstance(value, str):
            parts = value.split(delimiter)
            if 0 <= index < len(parts):
                return parts[index].strip()
            return None

    elif t_type == "map":
        mapping = transform_def.get("mapping", {})
        default = transform_def.get("default", None) # If provided, use default on miss
        # If default is NOT provided, maybe return original? No, consistent with others: None or specific behavior.
        # Let's return original if no default specified, or None? 
        # Safest for "normalization": if not in map, keep original.
        return mapping.get(str(value), default if "default" in transform_def else value)
        
    elif t_type == "clean":
        if isinstance(value, str):
            # normalize whitespace
            return re.sub(r"\s+", " ", value).strip()
            
    return value
