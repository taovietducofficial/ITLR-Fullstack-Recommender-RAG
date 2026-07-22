def fact_table_is_valid(null_keys: int, negative_amounts: int) -> bool:
    return null_keys == 0 and negative_amounts == 0


def customer_dim_is_unique(total_rows: int, distinct_rows: int) -> bool:
    return total_rows == distinct_rows


def itlr_fact_interaction_is_valid(null_keys: int) -> bool:
    return null_keys == 0
