from __future__ import annotations
import json
import re
from copy import deepcopy

class ActionError(RuntimeError): pass

def resolve_template(value, variables):
    if isinstance(value, dict): return {k: resolve_template(v, variables) for k, v in value.items()}
    if isinstance(value, list): return [resolve_template(v, variables) for v in value]
    if isinstance(value, str) and value.startswith("$"):
        key = value[1:]
        if key not in variables: raise ActionError(f"Unknown template variable: {value}")
        return variables[key]
    return value

def descriptor(tool_map, key):
    d = tool_map.get(key)
    if not isinstance(d, dict) or not d.get("tool"):
        raise ActionError(f"Tool mapping {key!r} is not configured. Run inspect-tools and edit config/tool-map.json.")
    return d

def call_descriptor(client, tool_map, key, variables=None):
    d = descriptor(tool_map, key)
    args = resolve_template(d.get("args", {}), variables or {})
    return client.call(d["tool"], args)

def path_get(obj, path):
    if not path: return obj
    cur = obj
    for part in path.split("."):
        if isinstance(cur, str):
            try: cur = json.loads(cur)
            except Exception: raise KeyError(part)
        if isinstance(cur, dict): cur = cur[part]
        elif isinstance(cur, list): cur = cur[int(part)]
        else: raise KeyError(part)
    return cur

def extract_value(result, d, expected="number"):
    path = d.get("valuePath")
    if not path: raise ActionError(f"Mapping for {d.get('tool')} needs an explicit valuePath for safe read-back.")
    value = path_get(result, path)
    if isinstance(value, str):
        try: value = json.loads(value)
        except Exception: pass
        if isinstance(value, str) and expected == "number":
            m = re.search(r"-?\d+(?:\.\d+)?", value)
            if m: value = float(m.group(0))
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ActionError(f"Expected a numeric value at {path}; got {value!r}")
        return float(value)
    if expected == "bool":
        if isinstance(value, bool): return value
        if isinstance(value, str) and value.casefold() in {"true", "muted", "on", "yes"}: return True
        if isinstance(value, str) and value.casefold() in {"false", "unmuted", "off", "no"}: return False
        raise ActionError(f"Expected a boolean value at {path}; got {value!r}")
    return value

def parse_text_content(result):
    if isinstance(result, dict):
        contents = result.get("content", [])
        for item in contents:
            if item.get("type") == "text":
                t = item.get("text", "")
                try: return json.loads(t)
                except Exception: return t
    return result
