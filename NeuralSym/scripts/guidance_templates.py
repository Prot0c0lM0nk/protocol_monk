# guidance_templates.py
# Optimized guidance templates for small LLMs (8B models)

SMALL_MODEL_TEMPLATES = {
    "safety_first": """
CRITICAL CONSTRAINTS - MUST FOLLOW:
{risks}
""",
    "recommended_approach": """
RECOMMENDED APPROACH:
{recommendations}
""",
    "context_injection": """
VERIFIED FACTS:
{facts}
""",
    "structured_guidance": """
TASK: {intent}

CONSTRAINTS:
{risks_formatted}

RECOMMENDED STEPS:
{recommendations_formatted}

VERIFIED CONTEXT:
{facts_formatted}
""",
}


def format_risks_for_small_models(risks):
    """Format risks in a concise way suitable for small models"""
    if not risks:
        return "None - you can proceed safely"

    formatted = []
    for risk in risks[:3]:  # Limit to top 3 risks
        if isinstance(risk, str):
            formatted.append(f"- AVOID: {risk}")
        else:
            formatted.append(f"- AVOID: {risk}")
    return "\n".join(formatted)


def format_recommendations_for_small_models(recommendations):
    """Format recommendations in a clear, step-by-step manner"""
    if not recommendations:
        return "No specific recommendations available"

    formatted = []
    for i, rec in enumerate(recommendations[:3], 1):  # Limit to top 3
        if isinstance(rec, str):
            formatted.append(f"{i}. {rec}")
        else:
            formatted.append(f"{i}. {rec}")
    return "\n".join(formatted)


def format_facts_for_small_models(facts):
    """Format verified facts in a concise way"""
    if not facts:
        return "No verified facts available"

    formatted = []
    for fact in facts[:5]:  # Limit to top 5
        if isinstance(fact, dict):
            fact_type = fact.get("type", "fact")
            fact_value = fact.get("value", "")
            formatted.append(f"- {fact_type}: {fact_value}")
        else:
            formatted.append(f"- {fact}")
    return "\n".join(formatted)
