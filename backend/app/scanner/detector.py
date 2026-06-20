"""
ShadowScan Detection Engine
Detects suspicious prompt injection patterns across 7 categories.
Detection is case-insensitive and whitespace-tolerant.
"""

import re
from dataclasses import dataclass
from typing import List, Dict
from app.scanner.extractor import ExtractedContent


@dataclass
class DetectionMatch:
    """Represents a detected suspicious pattern."""
    category: str           # e.g., "Instruction Override"
    matched_rule: str       # The specific rule/phrase that matched
    evidence: str           # The full extracted content containing the match
    source_type: str        # Where it was found (e.g., "HTML Comment")
    element_context: str    # HTML context of the element
    impact: str             # Description of potential impact
    remediation: str        # Recommended fix


# --- Detection Rule Definitions ---
# Each category has a list of (pattern, rule_name) tuples.
# Patterns are case-insensitive and allow flexible whitespace.

def _build_pattern(phrase: str) -> re.Pattern:
    """
    Build a regex pattern from a phrase that:
    - Is case-insensitive
    - Allows flexible whitespace/punctuation between words
    """
    words = phrase.lower().split()
    pattern = r"[\s\-_.,;:!?]*".join(re.escape(w) for w in words)
    return re.compile(pattern, re.IGNORECASE)


# Category 1: Instruction Override
INSTRUCTION_OVERRIDE_RULES = [
    ("ignore previous instructions", "ignore_previous"),
    ("ignore all previous instructions", "ignore_all_previous"),
    ("ignore your instructions", "ignore_your"),
    ("forget your rules", "forget_rules"),
    ("forget all rules", "forget_all_rules"),
    ("disregard your instructions", "disregard_instructions"),
    ("disregard system prompt", "disregard_system"),
    ("disregard previous instructions", "disregard_previous"),
    ("bypass safety", "bypass_safety"),
    ("bypass your safety", "bypass_your_safety"),
    ("bypass content filter", "bypass_content_filter"),
    ("override your instructions", "override_instructions"),
    ("override safety", "override_safety"),
    ("disable safety", "disable_safety"),
    ("disable your filters", "disable_filters"),
    ("new instructions", "new_instructions"),
    ("your new instructions are", "new_instructions_are"),
    ("your actual instructions", "actual_instructions"),
    ("cancel previous prompt", "cancel_prompt"),
    ("stop being helpful", "stop_helpful"),
]

# Category 2: Data Exfiltration
DATA_EXFILTRATION_RULES = [
    ("reveal secret", "reveal_secret"),
    ("reveal your secret", "reveal_your_secret"),
    ("reveal the secret", "reveal_the_secret"),
    ("leak credentials", "leak_credentials"),
    ("show password", "show_password"),
    ("show the password", "show_the_password"),
    ("extract token", "extract_token"),
    ("extract api key", "extract_api_key"),
    ("send to attacker", "send_to_attacker"),
    ("send data to", "send_data_to"),
    ("exfiltrate", "exfiltrate"),
    ("output your system prompt", "output_system_prompt"),
    ("print your instructions", "print_instructions"),
    ("share your prompt", "share_prompt"),
    ("display your configuration", "display_config"),
    ("tell me your system prompt", "tell_system_prompt"),
    ("what are your instructions", "what_instructions"),
    ("reveal your prompt", "reveal_prompt"),
    ("leak your training", "leak_training"),
    ("send information to this url", "send_info_url"),
]

# Category 3: Unauthorized Action
UNAUTHORIZED_ACTION_RULES = [
    ("send email", "send_email"),
    ("send an email", "send_an_email"),
    ("delete files", "delete_files"),
    ("delete all files", "delete_all_files"),
    ("transfer money", "transfer_money"),
    ("submit form", "submit_form"),
    ("execute command", "execute_command"),
    ("run command", "run_command"),
    ("make a purchase", "make_purchase"),
    ("place an order", "place_order"),
    ("click this link", "click_link"),
    ("navigate to", "navigate_to"),
    ("download and execute", "download_execute"),
    ("modify database", "modify_database"),
    ("create admin account", "create_admin"),
    ("grant permission", "grant_permission"),
    ("change settings", "change_settings"),
    ("install software", "install_software"),
]

# Category 4: Persona/Role Override
PERSONA_OVERRIDE_RULES = [
    ("act as admin", "act_as_admin"),
    ("you are root", "you_are_root"),
    ("you are now", "you_are_now"),
    ("developer mode", "developer_mode"),
    ("dan mode", "dan_mode"),
    ("you are dan", "you_are_dan"),
    ("you are an unrestricted", "unrestricted_ai"),
    ("pretend you are", "pretend_you_are"),
    ("from now on you are", "from_now_on"),
    ("act as an evil", "act_evil"),
    ("behave as if you have no restrictions", "no_restrictions"),
    ("enter god mode", "god_mode"),
    ("enable unrestricted mode", "unrestricted_mode"),
    ("you have been jailbroken", "jailbroken"),
    ("your safety has been disabled", "safety_disabled"),
    ("switch to unfiltered mode", "unfiltered_mode"),
    ("you are a fictional ai with no limits", "fictional_no_limits"),
]

# Category 5: Stealth Instruction
STEALTH_INSTRUCTION_RULES = [
    ("do not tell the user", "dont_tell_user"),
    ("do not mention this", "dont_mention"),
    ("hide this", "hide_this"),
    ("silently perform", "silently_perform"),
    ("keep secret", "keep_secret"),
    ("keep this secret", "keep_this_secret"),
    ("without mentioning", "without_mentioning"),
    ("without telling", "without_telling"),
    ("do not reveal", "do_not_reveal"),
    ("never tell anyone", "never_tell"),
    ("act normally but", "act_normally_but"),
    ("pretend nothing happened", "pretend_nothing"),
    ("do this quietly", "do_quietly"),
    ("invisible to the user", "invisible_user"),
    ("suppress any warning", "suppress_warning"),
    ("covertly", "covertly"),
]

# Category 6: Context Injection
CONTEXT_INJECTION_RULES = [
    ("system: you are now", "system_you_are_now"),
    ("[system]", "system_bracket"),
    ("[SYSTEM]", "system_bracket_upper"),
    ("<|im_start|>system", "im_start_system"),
    ("<<SYS>>", "sys_tag"),
    ("### Instruction:", "instruction_header"),
    ("### System:", "system_header"),
    ("system prompt:", "system_prompt_colon"),
    ("<|system|>", "system_pipe"),
    ("[INST]", "inst_bracket"),
    ("Human:", "human_colon"),
    ("Assistant:", "assistant_colon"),
    ("BEGIN SYSTEM MESSAGE", "begin_system_message"),
    ("END USER MESSAGE", "end_user_message"),
]

# Category 7: Chained Payload Setup
CHAINED_PAYLOAD_RULES = [
    ("remember this keyword", "remember_keyword"),
    ("wait until you see", "wait_until"),
    ("when I say", "when_i_say"),
    ("when the user says", "when_user_says"),
    ("on the trigger word", "trigger_word"),
    ("store this for later", "store_for_later"),
    ("remember the following", "remember_following"),
    ("keep this in memory", "keep_in_memory"),
    ("use this later", "use_later"),
    ("activate when", "activate_when"),
    ("this is step one", "step_one"),
    ("in the next message", "next_message"),
    ("upon receiving the code word", "code_word"),
    ("first part of instruction", "first_part"),
]


# Map categories to their rule lists and metadata
CATEGORY_RULES: Dict[str, dict] = {
    "Instruction Override": {
        "rules": INSTRUCTION_OVERRIDE_RULES,
        "impact": "An AI system processing this content may ignore its safety instructions and original purpose, potentially producing harmful or unintended output.",
        "remediation": "Remove or sanitize hidden instructional text. Implement input validation that strips prompt-like patterns before passing content to an AI model. Use instruction-data separation techniques.",
    },
    "Data Exfiltration": {
        "rules": DATA_EXFILTRATION_RULES,
        "impact": "An AI system may be manipulated into revealing sensitive information such as API keys, system prompts, internal configurations, or user data to unauthorized parties.",
        "remediation": "Remove all data-exfiltration instructions. Implement output filtering on the AI system to detect and block sensitive data leakage. Use least-privilege principles for AI model access.",
    },
    "Unauthorized Action": {
        "rules": UNAUTHORIZED_ACTION_RULES,
        "impact": "An AI agent processing this content may execute unauthorized actions such as sending emails, modifying data, making purchases, or interacting with external systems without user consent.",
        "remediation": "Remove action-triggering instructions. Implement action confirmation workflows that require explicit user approval. Restrict AI agent capabilities using allowlists.",
    },
    "Persona/Role Override": {
        "rules": PERSONA_OVERRIDE_RULES,
        "impact": "An AI system may adopt a new persona or role that bypasses its safety guidelines, potentially producing harmful, unfiltered, or misleading content.",
        "remediation": "Remove persona override instructions. Strengthen the AI model's system prompt to resist role manipulation. Implement output monitoring for persona shifts.",
    },
    "Stealth Instruction": {
        "rules": STEALTH_INSTRUCTION_RULES,
        "impact": "An AI system may perform actions covertly without informing the user, making malicious behavior harder to detect and enabling hidden manipulation.",
        "remediation": "Remove stealth instructions. Implement transparency requirements in the AI system that force disclosure of all actions taken. Add audit logging.",
    },
    "Context Injection": {
        "rules": CONTEXT_INJECTION_RULES,
        "impact": "An attacker may inject fake system messages or context markers that the AI interprets as trusted instructions, potentially overriding its real system prompt.",
        "remediation": "Remove injected context markers. Implement strict message format validation. Use delimiter tokens that are unique and not guessable by attackers.",
    },
    "Chained Payload Setup": {
        "rules": CHAINED_PAYLOAD_RULES,
        "impact": "This content sets up a delayed or multi-step attack where the initial payload primes the AI for a later exploit, making the attack harder to detect in isolation.",
        "remediation": "Remove trigger/memory instructions. Implement stateless AI sessions where possible. Monitor for cross-message instruction patterns.",
    },
}


# Pre-compile all patterns for performance
_compiled_rules: Dict[str, List[tuple]] = {}
for category, info in CATEGORY_RULES.items():
    _compiled_rules[category] = [
        (_build_pattern(phrase), rule_name, phrase)
        for phrase, rule_name in info["rules"]
    ]


def detect_patterns(extracted_content: List[ExtractedContent]) -> List[DetectionMatch]:
    """
    Run all 7 detection categories against extracted content.
    Returns a list of DetectionMatch instances, deduplicated.
    """
    matches: List[DetectionMatch] = []
    seen = set()  # (source_type, content_hash, category, rule_name)

    for item in extracted_content:
        content_to_check = item.content

        for category, compiled_list in _compiled_rules.items():
            category_info = CATEGORY_RULES[category]

            for pattern, rule_name, original_phrase in compiled_list:
                if pattern.search(content_to_check):
                    # Dedup key: avoid reporting same rule match for same content from same source
                    dedup_key = (item.source_type, hash(item.content[:200]), category, rule_name)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    matches.append(DetectionMatch(
                        category=category,
                        matched_rule=original_phrase,
                        evidence=item.content,
                        source_type=item.source_type,
                        element_context=item.element_context,
                        impact=category_info["impact"],
                        remediation=category_info["remediation"],
                    ))

    return matches
