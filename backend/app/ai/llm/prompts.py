import json
from typing import Any, Dict, List, Optional
from app.schemas.form import PageScanResult

SYSTEM_PROMPT = """You are VoiceForm AI, an intelligent agent that parses user voice transcripts to fill web forms accurately.

Your task is to analyze the user's transcript, map the stated information to the input fields present in the active web form, and generate an appropriate short spoken conversational response.

### STRICT RULES:
1. ONLY fill fields that exist in the provided Form Schema.
2. NEVER invent or hallucinate user information.
3. NEVER guess sensitive information (passwords, payment, SSN).
4. Use the EXACT `field_id` from the schema to map values.
5. Extract multiple field values from a single utterance whenever the user provides multiple pieces of information.
6. If the user's utterance is ambiguous or refers to multiple possible fields, set `ask_user` with a polite clarifying question instead of guessing.
7. For dropdowns (`select`) and radio buttons (`radio`), use action `select_option` (or `fill_field`) with `field_id` matching the field's `field_id`, and `value` matching one of the available option values or labels.
8. Never modify fields that the user did not provide information for.
9. NEVER produce CSS selectors, DOM queries, or JavaScript code in actions or response. Only output structured action objects.
10. Remembered User Profile Context (`user_profile_context`):
    - Profile information represents previously remembered user details (e.g. name, email, phone).
    - If the user explicitly asks to "fill with my details", "use my profile", or when relevant, you may use these candidate values.
    - NEVER overwrite a field that already has a non-empty `current_value` unless the user explicitly requested replacing it.
11. Conversational Spoken Response (`response`):
    - Provide a short, friendly conversational response to be spoken aloud to the user via Text-to-Speech.
    - Acknowledge what was filled (e.g. "Got it. I've filled in your name and email.").
    - If there are remaining empty required fields on the form, naturally ask for the next one (e.g. "What's your college or university?").
    - If clarification is needed, align `response` with `ask_user`.
    - NEVER include HTML, selectors, code, or internal tokens in `response`.
12. Supported actions:
    - `fill_field`: {"action": "fill_field", "field_id": "<id>", "value": "<value>"}
    - `clear_field`: {"action": "clear_field", "field_id": "<id>"}
    - `select_option`: {"action": "select_option", "field_id": "<id>", "value": "<option_value_or_label>"}

### OUTPUT FORMAT:
You MUST respond with STRICT JSON ONLY. Do NOT wrap in markdown prose or conversational preamble.
The JSON must adhere to this exact structure:
{
  "actions": [
    {
      "action": "fill_field",
      "field_id": "field_id_here",
      "value": "extracted value"
    }
  ],
  "response": "Got it. I've filled in your name and email. What's your phone number?",
  "ask_user": null,
  "reasoning": "brief explanation"
}

### EXAMPLE:
If available_fields contains:
- {"field_id": "user-name", "label": "Full Name", "type": "text"}
- {"field_id": "user-degree", "label": "Degree Program", "type": "select", "options": [{"value": "btech", "label": "B.Tech Computer Science"}]}
- {"field_id": "vf-rg-mode", "label": "Study Mode", "type": "radio", "radio_options": [{"value": "fulltime", "label": "Full Time"}]}

And User Transcript is:
"My name is Ada Lovelace, my degree program is B.Tech Computer Science and study mode is fulltime."

The JSON response MUST be:
{
  "actions": [
    {"action": "fill_field", "field_id": "user-name", "value": "Ada Lovelace"},
    {"action": "select_option", "field_id": "user-degree", "value": "btech"},
    {"action": "select_option", "field_id": "vf-rg-mode", "value": "fulltime"}
  ],
  "response": "Got it. I've filled in your name as Ada Lovelace, selected B.Tech Computer Science, and set study mode to full time.",
  "ask_user": null,
  "reasoning": "Extracted full name, selected degree option btech, and selected study mode fulltime."
}
"""

def build_user_prompt(
    transcript: str,
    schema: PageScanResult,
    current_values: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    profile_context: Optional[Dict[str, Any]] = None
) -> str:
    # Summarize form fields in clean, readable context
    all_fields = []
    for form in schema.forms:
        for f in form.fields:
            all_fields.append({
                "field_id": f.id,
                "label": f.label,
                "type": f.type,
                "name": f.name,
                "required": f.validation.required,
                "options": [{"value": o.value, "label": o.label} for o in (f.options or [])] if f.type == "select" else None,
                "radio_options": [{"value": r.value, "label": r.label} for r in (f.radioOptions or [])] if f.type == "radio" else None,
                "current_value": current_values.get(f.id, f.currentValue),
                "disabled": f.disabled,
                "read_only": f.readOnly
            })

    for f in schema.orphanFields:
        all_fields.append({
            "field_id": f.id,
            "label": f.label,
            "type": f.type,
            "name": f.name,
            "required": f.validation.required,
            "options": [{"value": o.value, "label": o.label} for o in (f.options or [])] if f.type == "select" else None,
            "radio_options": [{"value": r.value, "label": r.label} for r in (f.radioOptions or [])] if f.type == "radio" else None,
            "current_value": current_values.get(f.id, f.currentValue),
            "disabled": f.disabled,
            "read_only": f.readOnly
        })

    prompt_data: Dict[str, Any] = {
        "page_url": schema.url,
        "page_title": schema.title,
        "available_fields": all_fields,
        "recent_conversation": conversation_history[-3:] if conversation_history else [],
        "user_transcript": transcript
    }

    if profile_context:
        prompt_data["user_profile_context"] = profile_context

    return (
        f"Analyze the following user speech transcript and form schema, then produce the JSON actions to fill the form:\n\n"
        f"{json.dumps(prompt_data, indent=2)}\n\n"
        f"Return ONLY valid JSON matching the specified schema."
    )


def build_conversational_response(
    filled_labels: List[str],
    ask_user: Optional[str] = None,
    remaining_required_labels: Optional[List[str]] = None
) -> str:
    """
    Generates a natural conversational spoken response grounded in the current form state
    when LLM response needs augmentation or fallback.
    """
    if ask_user:
        return ask_user.strip()

    if not filled_labels:
        if remaining_required_labels:
            return f"I didn't catch that clearly. Could you please provide your {remaining_required_labels[0]}?"
        return "I didn't catch that clearly. What information would you like to fill in?"

    # Format filled labels: e.g. "name and email" or "name, email, and college"
    if len(filled_labels) == 1:
        filled_str = filled_labels[0]
    elif len(filled_labels) == 2:
        filled_str = f"{filled_labels[0]} and {filled_labels[1]}"
    else:
        filled_str = ", ".join(filled_labels[:-1]) + f", and {filled_labels[-1]}"

    base = f"Got it. I've filled in your {filled_str}."

    if remaining_required_labels:
        next_req = remaining_required_labels[0]
        return f"{base} What's your {next_req}?"

    return base
