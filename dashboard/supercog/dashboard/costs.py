def cents_per_1k(dollars_per_million: float):
    return (dollars_per_million * 100.0) / 1000.0

# cost in "cents per 1k tokens" converted from "dollars per million" tokens
MODEL_COSTS = {
    "claude-3-5-sonnet": [cents_per_1k(3), cents_per_1k(15)],
    "claude-3-opus": [cents_per_1k(15), cents_per_1k(75)],
    "claude-3-sonnet": [cents_per_1k(3), cents_per_1k(15)],
    "gpt-4-": [cents_per_1k(10), cents_per_1k(30)],
    "gpt-4": [cents_per_1k(10), cents_per_1k(30)],
    "gpt-4o": [cents_per_1k(5), cents_per_1k(15)],
    "gpt-4o-mini": [cents_per_1k(0.15), cents_per_1k(0.60)],
}

def get_model_price(model: str):
    # exact match
    if model in MODEL_COSTS:
        return MODEL_COSTS[model]
    
    for comp in MODEL_COSTS.keys():
        if model.startswith(comp):
            return MODEL_COSTS[comp]
        
    return None

def calc_tokens_cents(model: str, input_tokens: int, output_tokens: int):
    # Returns the cost of token usage as tuple of input,ouput in total cents (divide by 100 for dollars)

    pricing: list[float] = get_model_price(model)
    if pricing is not None:
        return pricing[0] * (input_tokens/1000.0), pricing[1] * (output_tokens/1000.0)
    else:
        return [0,0]
