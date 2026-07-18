def build_merge_condition(keys) -> str:
    return " AND ".join(f"t.{key} = s.{key}" for key in keys)
