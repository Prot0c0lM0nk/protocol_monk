from agent.model_manager.structs import ModelInfo, SwitchReport
from agent.model_manager.loader import ModelConfigLoader
from typing import Dict

class ModelSelector:
    """Implements the guardrail logic for model switching."""
    
    def __init__(self, model_map: Dict[str, ModelInfo]):
        self.model_map = model_map
    
    def assess_switch(self, current_usage: int, target_model_name: str) -> SwitchReport:
        """Assess if it's safe to switch to the target model."""
        target_model = self.model_map.get(target_model_name)
        
        if not target_model:
            return SwitchReport(
                safe=False,
                current_tokens=current_usage,
                target_limit=0,
                recommendation="CANCEL",
                message=f"Target model {target_model_name} not found"
            )
        
        target_limit = target_model.context_window
        
        # Check if current usage exceeds target model's limit
        if current_usage <= target_limit:
            return SwitchReport(
                safe=True,
                current_tokens=current_usage,
                target_limit=target_limit,
                recommendation="SAFE",
                message="Safe to switch"
            )
        
        # Calculate how much we need to prune
        excess_tokens = current_usage - target_limit
        
        # Determine recommendation based on excess
        if excess_tokens > target_limit * 0.5:  # More than 50% over limit
            recommendation = "ARCHIVE"
            message = f"Context is {excess_tokens:,} tokens over limit. Consider archiving."
        else:
            recommendation = "PRUNE"
            message = f"Context is {excess_tokens:,} tokens over limit. Consider pruning."
        
        return SwitchReport(
            safe=False,
            current_tokens=current_usage,
            target_limit=target_limit,
            recommendation=recommendation,
            message=message
        )
