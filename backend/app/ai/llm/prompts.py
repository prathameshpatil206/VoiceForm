import json
from typing import Any, Dict, List, Optional
from app.schemas.form import PageScanResult

SYSTEM_PROMPT = """You are VoiceForm AI, an intelligent agent that parses user voice transcripts to fill web forms accurately and with blazing speed.

Your task is to analyze the user's spoken transcript, map the stated information to the input fields present in the active web form, and generate an appropriate short spoken conversational response.

### STRICT RULES:
1. ONLY fill fields that exist in the provided Form Schema.
2. The user's CURRENT spoken transcript ALWAYS takes 100% absolute precedence.
   - If the user states a name (e.g., "My name is Sai Siddu" or "Alex"), ALWAYS fill the exact stated value ("Sai Siddu"), NEVER an old or profile name.
   - ONLY use candidate values from `user_profile_context` if the user explicitly asks (e.g., "use my profile", "fill my saved info", "use my details") or asks to autofill without giving a value.
3. NEVER invent, hallucinate, or assume user information.
4. NEVER guess sensitive information (passwords, payment details, CVV).
5. Use the EXACT `field_id` from the schema to map values.
6. Extract multiple field values from a single utterance whenever the user provides multiple pieces of information (e.g. "My name is Prathamesh, email is p@test.com, phone 555-1234").
7. If the user's utterance is ambiguous or refers to multiple possible fields, set `ask_user` with a polite clarifying question instead of guessing.
8. For dropdowns (`select`) and radio buttons (`radio`), use action `select_option` (or `fill_field`) with `field_id` matching the field's `field_id`, and `value` matching one of the available option values or labels.
9. Never modify fields that the user did not provide information for.
10. NEVER produce CSS selectors, DOM queries, or JavaScript code in actions or response.
11. Conversational Spoken Response (`response`):
    - Provide a concise, friendly conversational response to be spoken aloud to the user via Text-to-Speech.
    - Acknowledge what was filled (e.g. "Got it. I've filled in your name and email.").
    - If there are remaining empty required fields on the form, naturally ask for the next one (e.g. "What's your college or university?").
    - If clarification is needed, align `response` with `ask_user`.
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

And User Transcript is:
"My name is Sai Siddu and my degree program is B.Tech Computer Science."

The JSON response MUST be:
{
  "actions": [
    {"action": "fill_field", "field_id": "user-name", "value": "Sai Siddu"},
    {"action": "select_option", "field_id": "user-degree", "value": "btech"}
  ],
  "response": "Got it. I've filled in your name as Sai Siddu and selected B.Tech Computer Science.",
  "ask_user": null,
  "reasoning": "Extracted full name as Sai Siddu and selected degree option btech."
}
"""

def build_user_prompt(
    transcript: str,
    schema: PageScanResult,
    current_values: Dict[str, Any],
    conversation_history: List[Dict[str, Any]],
    profile_context: Optional[Dict[str, Any]] = None
) -> str:
    # Summarize form fields in clean, compact context
    all_fields = []
    for form in schema.forms:
        for f in form.fields:
            item: Dict[str, Any] = {
                "field_id": f.id,
                "label": f.label,
                "type": f.type
            }
            if f.name:
                item["name"] = f.name
            if f.validation.required:
                item["required"] = True
            if f.type == "select" and f.options:
                item["options"] = [{"value": o.value, "label": o.label} for o in f.options]
            if f.type == "radio" and f.radioOptions:
                item["radio_options"] = [{"value": r.value, "label": r.label} for r in f.radioOptions]
            curr = current_values.get(f.id, f.currentValue)
            if curr:
                item["current_value"] = curr
            if f.disabled:
                item["disabled"] = True
            all_fields.append(item)

    for f in schema.orphanFields:
        item = {
            "field_id": f.id,
            "label": f.label,
            "type": f.type
        }
        if f.name:
            item["name"] = f.name
        if f.validation.required:
            item["required"] = True
        if f.type == "select" and f.options:
            item["options"] = [{"value": o.value, "label": o.label} for o in f.options]
        if f.type == "radio" and f.radioOptions:
            item["radio_options"] = [{"value": r.value, "label": r.label} for r in f.radioOptions]
        curr = current_values.get(f.id, f.currentValue)
        if curr:
            item["current_value"] = curr
        if f.disabled:
            item["disabled"] = True
        all_fields.append(item)

    prompt_data: Dict[str, Any] = {
        "page_title": schema.title or "Web Form",
        "available_fields": all_fields,
        "user_transcript": transcript
    }

    if conversation_history:
        prompt_data["recent_conversation"] = conversation_history[-2:]

    if profile_context:
        prompt_data["user_profile_context"] = profile_context

    return (
        f"Analyze user speech transcript and form fields, then produce JSON actions:\n\n"
        f"{json.dumps(prompt_data, separators=(',', ':'))}\n\n"
        f"Return ONLY valid JSON."
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


def heuristic_extract_actions(transcript: str, schema: PageScanResult) -> List[Dict[str, Any]]:
    """
    Sub-millisecond heuristic safety net. Extracts common form slots (first name,
    last name, full name, email, phone, etc.) directly from spoken speech patterns
    if the LLM fails or produces zero actions.
    """
    import re
    actions: List[Dict[str, Any]] = []
    if not transcript or not transcript.strip():
        return actions

    text = transcript.strip()

    # Collect all candidate fields
    all_fields = [f for form in schema.forms for f in form.fields] + list(schema.orphanFields)

    # 1. Email extraction
    email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    if not email_match:
        # Common spoken forms: "alex dot morgan at example dot com"
        spoken_email = re.search(
            r"([a-zA-Z0-9_.-]+)\s*(?:@|at)\s*([a-zA-Z0-9_.-]+)\s*(?:\.|\bdot\b)\s*([a-zA-Z]{2,6})",
            text,
            re.IGNORECASE
        )
        if spoken_email:
            email_val = f"{spoken_email.group(1)}@{spoken_email.group(2)}.{spoken_email.group(3)}".replace(" ", "").lower()
            email_match = True
        else:
            email_val = None
    else:
        email_val = email_match.group(1)

    if email_val:
        for f in all_fields:
            if f.type == "email" or any(k in f.id.lower() or k in (f.name or "").lower() or k in f.label.lower() for k in ["email", "mail"]):
                actions.append({"action": "fill_field", "field_id": f.id, "value": email_val})
                break

    # 2. Phone extraction
    phone_match = re.search(r"(?:phone|mobile|tel|contact)?(?:(?:\s+is|\s*:|\s+number\s+is)?\s*)([0-9\+\(\)\-\s]{7,15})", text, re.IGNORECASE)
    if phone_match:
        digits_only = re.sub(r"[^\d+]", "", phone_match.group(1))
        if len(digits_only) >= 7:
            for f in all_fields:
                if f.type == "tel" or any(k in f.id.lower() or k in (f.name or "").lower() or k in f.label.lower() for k in ["phone", "mobile", "tel"]):
                    actions.append({"action": "fill_field", "field_id": f.id, "value": phone_match.group(1).strip()})
                    break

    # 3. First Name / Last Name / Full Name
    # "My first name is X" or "first name is X"
    first_name_match = re.search(r"(?:my\s+)?first\s+name\s+(?:is\s+)?([A-Za-z]+)", text, re.IGNORECASE)
    # "My last name is Y" or "last name is Y"
    last_name_match = re.search(r"(?:my\s+)?last\s+name\s+(?:is\s+)?([A-Za-z]+)", text, re.IGNORECASE)

    if first_name_match:
        fn_val = first_name_match.group(1).strip().capitalize()
        for f in all_fields:
            if any(k in f.id.lower() or k in (f.name or "").lower() or k in f.label.lower() for k in ["first", "fname", "firstname"]):
                actions.append({"action": "fill_field", "field_id": f.id, "value": fn_val})
                break

    if last_name_match:
        ln_val = last_name_match.group(1).strip().capitalize()
        for f in all_fields:
            if any(k in f.id.lower() or k in (f.name or "").lower() or k in f.label.lower() for k in ["last", "lname", "lastname", "surname"]):
                actions.append({"action": "fill_field", "field_id": f.id, "value": ln_val})
                break

    # "My name is X Y" or "I am X Y"
    if not first_name_match:
        full_name_match = re.search(r"(?:my\s+name\s+is|i\s+am|this\s+is)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)", text, re.IGNORECASE)
        if full_name_match:
            raw_name = full_name_match.group(1).strip()
            name_parts = raw_name.split()
            if len(name_parts) >= 2:
                # Check if there are separate first & last name fields
                fn_field = next((f for f in all_fields if any(k in f.id.lower() or k in (f.name or "").lower() or k in f.label.lower() for k in ["first", "fname", "firstname"])), None)
                ln_field = next((f for f in all_fields if any(k in f.id.lower() or k in (f.name or "").lower() or k in f.label.lower() for k in ["last", "lname", "lastname", "surname"])), None)
                full_field = next((f for f in all_fields if any(k in f.id.lower() or k in (f.name or "").lower() or k in f.label.lower() for k in ["fullname", "name"]) and f != fn_field and f != ln_field), None)

                if fn_field and ln_field:
                    actions.append({"action": "fill_field", "field_id": fn_field.id, "value": name_parts[0].capitalize()})
                    actions.append({"action": "fill_field", "field_id": ln_field.id, "value": " ".join(name_parts[1:]).capitalize()})
                elif full_field:
                    actions.append({"action": "fill_field", "field_id": full_field.id, "value": " ".join([p.capitalize() for p in name_parts])})
                elif fn_field:
                    actions.append({"action": "fill_field", "field_id": fn_field.id, "value": name_parts[0].capitalize()})
            elif len(name_parts) == 1:
                # Single name
                fn_field = next((f for f in all_fields if any(k in f.id.lower() or k in (f.name or "").lower() or k in f.label.lower() for k in ["first", "name", "fname"])), None)
                if fn_field:
                    actions.append({"action": "fill_field", "field_id": fn_field.id, "value": name_parts[0].capitalize()})

    # Deduplicate actions by field_id
    seen_ids = set()
    deduped = []
    for a in actions:
        if a["field_id"] not in seen_ids:
            seen_ids.add(a["field_id"])
            deduped.append(a)

    return deduped

