import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx

from app.ai.llm.base import LLMActionResult, LLMProvider
from app.ai.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.config import config
from app.schemas.form import PageScanResult

logger = logging.getLogger("voiceform.llm.qwen")

class Qwen3LLMProvider(LLMProvider):
    """
    Qwen3 LLM provider for reasoning, semantic entity recognition,
    and structured form action extraction.
    Supports high-speed cloud LLMs (Groq) and optimized local Ollama.
    """

    def __init__(
        self,
        base_url: str = config.OLLAMA_BASE_URL,
        model_name: str = config.LLM_MODEL,
        timeout_seconds: float = config.LLM_TIMEOUT,
        groq_api_key: Optional[str] = os.getenv("GROQ_API_KEY")
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.groq_api_key = groq_api_key if groq_api_key and groq_api_key != "your_groq_api_key_here" else None

    async def extract_actions(
        self,
        transcript: str,
        schema: PageScanResult,
        current_values: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        profile_context: Optional[Dict[str, Any]] = None
    ) -> LLMActionResult:
        # 1. High-speed cloud LLM (Groq) if configured (sub-250ms latency)
        groq_key = self.groq_api_key or os.getenv("GROQ_API_KEY")
        if groq_key and groq_key != "your_groq_api_key_here":
            try:
                return await self._extract_via_groq(
                    transcript, schema, current_values, conversation_history, profile_context, groq_key
                )
            except Exception as e_groq:
                logger.warning(f"Groq LLM extraction failed; falling back to local Ollama: {e_groq}")

        # 2. Local Ollama with speed optimization parameters
        user_prompt = build_user_prompt(
            transcript=transcript,
            schema=schema,
            current_values=current_values,
            conversation_history=conversation_history,
            profile_context=profile_context
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
                "top_p": 0.9,
                "num_predict": 600,   # Generous token limit to prevent truncated JSON
                "num_ctx": 2048,
                "num_thread": 8
            }
        }

        endpoint = f"{self.base_url}/api/chat"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                resp = await client.post(endpoint, json=payload)
                if resp.status_code == 404:
                    try:
                        tags_resp = await client.get(f"{self.base_url}/api/tags")
                        if tags_resp.status_code == 200:
                            models_data = tags_resp.json().get("models", [])
                            model_names = [m.get("name", "") for m in models_data]
                            chosen = next((m for m in model_names if "qwen" in m.lower()), None)
                            if not chosen and model_names:
                                chosen = model_names[0]
                            if chosen and chosen != self.model_name:
                                logger.info(f"Model '{self.model_name}' not found. Auto-selected '{chosen}' from Ollama.")
                                self.model_name = chosen
                                payload["model"] = chosen
                                resp = await client.post(endpoint, json=payload)
                    except Exception as tag_err:
                        logger.debug(f"Could not auto-discover Ollama tags: {tag_err}")

                if resp.status_code == 404:
                    endpoint = f"{self.base_url}/v1/chat/completions"
                    payload["response_format"] = {"type": "json_object"}
                    resp = await client.post(endpoint, json=payload)

                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"Error calling LLM provider at {endpoint}: {e}")
                raise

        raw_content = ""
        if "message" in data and "content" in data["message"]:
            raw_content = data["message"]["content"]
        elif "choices" in data and len(data["choices"]) > 0:
            raw_content = data["choices"][0].get("message", {}).get("content", "")
        else:
            raw_content = str(data)

        return self._parse_llm_output(raw_content)

    async def _extract_via_groq(
        self,
        transcript: str,
        schema: PageScanResult,
        current_values: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        profile_context: Optional[Dict[str, Any]],
        api_key: str
    ) -> LLMActionResult:
        """Sub-100ms ultra-fast Groq LLM inference using active high-speed models."""
        user_prompt = build_user_prompt(
            transcript=transcript,
            schema=schema,
            current_values=current_values,
            conversation_history=conversation_history,
            profile_context=profile_context
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        # Primary model: openai/gpt-oss-20b (~70ms latency, strict JSON support)
        # High-capacity fallbacks: openai/gpt-oss-120b, groq/compound-mini, qwen/qwen3.8-27b
        candidate_models = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "groq/compound-mini", "qwen/qwen3.8-27b"]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=8.0) as client:
            last_err = None
            for model_name in candidate_models:
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.0,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"}
                }
                try:
                    resp = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        logger.info(f"⚡ Groq LLM extraction succeeded using model '{model_name}'")
                        return self._parse_llm_output(content)
                    else:
                        logger.warning(f"Groq model '{model_name}' returned status {resp.status_code}: {resp.text[:120]}")
                        last_err = RuntimeError(f"Groq {model_name} status {resp.status_code}")
                except Exception as e_m:
                    logger.warning(f"Groq call to '{model_name}' failed: {e_m}")
                    last_err = e_m

            if last_err:
                raise last_err
            raise RuntimeError("All Groq model attempts exhausted.")

    def _parse_llm_output(self, raw_text: str) -> LLMActionResult:
        """Parse strict JSON output from LLM, handling markdown code fences, think tags, and malformed variants."""
        cleaned = raw_text.strip()

        # 1. Strip <think>...</think> blocks from reasoning models (e.g. Qwen / DeepSeek)
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

        # 2. Strip markdown code fences
        if "```" in cleaned:
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned).strip()

        parsed: Optional[Dict[str, Any]] = None
        try:
            parsed = json.loads(cleaned)
        except Exception:
            # Try to extract the first balanced JSON object {...}
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                except Exception:
                    # Attempt simple JSON truncation repair if unterminated
                    candidate = match.group(1).rstrip()
                    for closer in ['"}', '"}]}', '"]}', '"}', '}']:
                        try:
                            parsed = json.loads(candidate + closer)
                            break
                        except Exception:
                            continue

        if not parsed or not isinstance(parsed, dict):
            logger.warning(f"Failed to parse LLM JSON. Raw content was: {raw_text[:200]}")
            return LLMActionResult(actions=[], reasoning="Malformed JSON from LLM")

        # 3. Handle cases where model echoed 'fields' or used alternate action keys
        raw_actions = parsed.get("actions", [])
        if not raw_actions and "fields" in parsed and isinstance(parsed["fields"], list):
            # Model outputted fields list with values
            recovered_actions = []
            for f in parsed["fields"]:
                if isinstance(f, dict) and "field_id" in f and ("value" in f or "current_value" in f):
                    val = f.get("value") or f.get("current_value")
                    if val is not None and str(val).strip():
                        recovered_actions.append({
                            "action": "fill_field",
                            "field_id": f["field_id"],
                            "value": val
                        })
            raw_actions = recovered_actions

        # Normalize action items: ensure action key is present
        normalized_actions = []
        if isinstance(raw_actions, list):
            for act in raw_actions:
                if isinstance(act, dict):
                    act_type = act.get("action") or act.get("type") or "fill_field"
                    field_id = act.get("field_id") or act.get("id")
                    value = act.get("value")
                    if field_id is not None:
                        normalized_actions.append({
                            "action": str(act_type),
                            "field_id": str(field_id),
                            "value": value
                        })

        response_text = parsed.get("response")
        ask_user = parsed.get("ask_user")
        reasoning = parsed.get("reasoning")

        return LLMActionResult(
            actions=normalized_actions,
            response=str(response_text).strip() if response_text else None,
            ask_user=str(ask_user).strip() if ask_user else None,
            reasoning=str(reasoning).strip() if reasoning else None
        )
