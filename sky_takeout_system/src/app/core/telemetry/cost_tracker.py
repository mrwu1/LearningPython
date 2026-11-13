from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ModelPricing:
    """Pricing per 1M tokens in USD."""
    prompt_price_per_m: float
    completion_price_per_m: float
    cache_hit_price_per_m: float = 0.0


# Default provider pricing table per 1M tokens in USD
DEFAULT_PRICING_TABLE: Dict[str, ModelPricing] = {
    "deepseek-chat": ModelPricing(prompt_price_per_m=0.14, completion_price_per_m=0.28, cache_hit_price_per_m=0.014),
    "deepseek-reasoner": ModelPricing(prompt_price_per_m=0.55, completion_price_per_m=2.19),
    "gpt-4o-mini": ModelPricing(prompt_price_per_m=0.15, completion_price_per_m=0.60),
    "gpt-4o": ModelPricing(prompt_price_per_m=2.50, completion_price_per_m=10.00),
}


@dataclass
class TokenUsageReport:
    """Detailed token consumption and billing breakdown for an agent interaction."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


class TokenCostCalculator:
    """Calculates exact financial cost based on provider pricing tables."""

    @staticmethod
    def calculate(
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_hit_tokens: int = 0
    ) -> TokenUsageReport:
        pricing = DEFAULT_PRICING_TABLE.get(model_name)
        if not pricing:
            pricing = DEFAULT_PRICING_TABLE["deepseek-chat"]

        uncached_prompt_tokens = max(0, prompt_tokens - cache_hit_tokens)
        prompt_cost = (uncached_prompt_tokens / 1_000_000.0) * pricing.prompt_price_per_m
        cache_cost = (cache_hit_tokens / 1_000_000.0) * pricing.cache_hit_price_per_m
        completion_cost = (completion_tokens / 1_000_000.0) * pricing.completion_price_per_m

        total_cost = prompt_cost + cache_cost + completion_cost
        total_tokens = prompt_tokens + completion_tokens

        return TokenUsageReport(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=total_cost
        )
