"""
Simple Enhanced Knowledge Graph Demo
Shows key concepts without complex implementation
"""

# Key enhancements over current system:

# 1. Multi-layered knowledge representation
LAYERS = ["factual", "procedural", "strategic", "meta"]

# 2. Confidence decay over time
# Facts become less certain as they age


def apply_confidence_decay(confidence, age_days, decay_rate=0.01):
    """Apply temporal decay to confidence"""
    import math

    decay_factor = math.exp(-decay_rate * age_days)
    return confidence * decay_factor


# 3. Bayesian evidence updating
def update_confidence_bayesian(prior, likelihood):
    """Update confidence using Bayesian inference"""
    posterior = (likelihood * prior) / (
        (likelihood * prior) + (1 - likelihood) * (1 - prior)
    )
    return min(0.999, posterior)


# 4. Cross-validation
def check_consistency(facts):
    """Check consistency between related facts"""
    if len(facts) < 2:
        return 1.0

    # Simple agreement check
    statuses = [fact["status"] for fact in facts]
    agreement = max(statuses.count(s) for s in set(statuses))
    return agreement / len(statuses)


# Example usage
def demo():
    print("=== Enhanced Knowledge Graph Concepts ===\n")

    # Create a fact with high confidence
    fact = {
        "id": "fact_001",
        "type": "tool_success",
        "value": "head -50 file.txt works for large files",
        "confidence": 0.9,
        "status": "verified",
        "layer": "procedural",
        "created_at": 0,  # days ago
        "access_count": 5,
    }

    print("1. Initial fact:")
    print(f"   Confidence: {fact['confidence']:.3f}")
    print(f"   Layer: {fact['layer']}")
    print(f"   Status: {fact['status']}\n")

    # Apply confidence decay (fact is 30 days old)
    print("2. After 30 days:")
    decayed_conf = apply_confidence_decay(fact["confidence"], 30)
    print(f"   Decayed confidence: {decayed_conf:.3f}\n")

    # Add new evidence (Bayesian update)
    print("3. Adding new evidence (strength 0.8):")
    updated_conf = update_confidence_bayesian(decayed_conf, 0.8)
    print(f"   Updated confidence: {updated_conf:.3f}\n")

    # Cross-validation example
    print("4. Cross-validation:")
    related_facts = [
        {"status": "verified", "confidence": 0.9},
        {"status": "verified", "confidence": 0.85},
        {"status": "refuted", "confidence": 0.2},
    ]
    consistency = check_consistency(related_facts)
    print(f"   Consistency score: {consistency:.3f}")
    print(f"   {'High' if consistency > 0.8 else 'Low'} consistency\n")

    print("=== Key Enhancements Summary ===")
    print("1. Multi-layered knowledge (factual/procedural/strategic/meta)")
    print("2. Temporal confidence decay")
    print("3. Bayesian evidence updating")
    print("4. Cross-validation for consistency")
    print("5. Context-aware retrieval")


if __name__ == "__main__":
    demo()
