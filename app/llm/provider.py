import json
import re
import requests
from typing import Dict, Any, Optional
from app.core.config import config
from app.core.logging_config import logger
from app.tools.secret_scanner import SecretScanner

class LLMProvider:
    """Unified LLM interface supporting Google Gemini, Mistral Cloud, and Mistral Local."""

    @staticmethod
    def _clean_json_response(raw_text: str) -> Dict[str, Any]:
        """Strips markdown code fences and safely parses JSON with robust error repair."""
        if not raw_text:
            return {}
        
        # 1. Try ```json ... ``` blocks first
        json_matches = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_text)
        for cand in json_matches:
            try:
                return json.loads(cand, strict=False)
            except Exception:
                pass

        # 2. Try outermost { ... }
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
        cleaned = match.group(1).strip() if match else raw_text.strip()

        if not cleaned.startswith("{") and "{" in cleaned:
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                cleaned = cleaned[start_idx:end_idx + 1]

        try:
            return json.loads(cleaned, strict=False)
        except Exception:
            try:
                # Remove trailing commas before } or ]
                repaired = re.sub(r",\s*([\]}])", r"\1", cleaned)
                # Add missing comma between adjacent properties: "value"\n  "key":
                repaired = re.sub(r'("[\s\S]*?"|\d+|true|false|null)\s*\n\s*(")', r'\1,\n\2', repaired)
                return json.loads(repaired, strict=False)
            except Exception as e:
                logger.warning(f"Failed to parse LLM JSON: {e}. Raw: {raw_text[:200]}")
                return {"raw_output": raw_text}

    @classmethod
    def generate(cls, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Invokes the configured LLM provider directly with automatic fallback for high reliability."""
        safe_prompt = SecretScanner.redact_text(prompt)
        mode = (config.MODE or "Gemini").strip().lower()

        if mode in ("mistral", "local"):
            logger.info(f"Executing dynamic LLM review via Mistral (URL: {config.MISTRAL_LOCAL_URL or 'Cloud API'})...")
            try:
                return cls._call_mistral(safe_prompt, system_prompt, force_local=(mode == "local"))
            except Exception as e:
                logger.warning(f"Mistral provider failed or timed out ({e}). Falling back to Gemini...")
                if config.GEMINI_API_KEY:
                    return cls._call_gemini(safe_prompt, system_prompt)
                raise
        else:
            logger.info(f"Executing dynamic LLM review via Gemini ({config.GEMINI_MODEL or 'gemini-2.5-flash'})...")
            try:
                return cls._call_gemini(safe_prompt, system_prompt)
            except Exception as e:
                logger.warning(f"Gemini API failed ({e}). Attempting fallback to Mistral...")
                if config.MISTRAL_LOCAL_URL or config.MISTRAL_API_KEY:
                    return cls._call_mistral(safe_prompt, system_prompt, force_local=bool(config.MISTRAL_LOCAL_URL))
                raise

    @classmethod
    def _call_gemini(cls, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Calls Google Gemini using the REST API with automatic multi-model failover."""
        api_key = config.GEMINI_API_KEY
        primary_model = config.GEMINI_MODEL or "gemini-2.5-flash"
        # Verified working models in order of speed and stability
        candidate_models = [primary_model, "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-flash-latest"]
        # Remove duplicates while preserving order
        candidate_models = list(dict.fromkeys(candidate_models))

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow all instructions and return valid JSON."}]})
        
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        last_error = "Unknown error"
        for model_name in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    text_content = data["candidates"][0]["content"]["parts"][0]["text"]
                    return cls._clean_json_response(text_content)
                else:
                    last_error = f"Gemini API error for model {model_name} (Status {resp.status_code}): {resp.text[:200]}"
                    logger.warning(last_error)
            except Exception as ex:
                last_error = f"Gemini request exception for model {model_name}: {ex}"
                logger.warning(last_error)

        logger.error(f"All Gemini model candidates failed. Last error: {last_error}")
        raise Exception(last_error)

    @classmethod
    def _call_mistral(cls, prompt: str, system_prompt: Optional[str] = None, force_local: bool = False) -> Dict[str, Any]:
        """Calls Mistral Cloud or Local Mistral Endpoint with 25s timeout and fallback support."""
        if config.MISTRAL_API_KEY and not force_local:
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {config.MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            }
            model = config.MODEL_NAME or "mistral-small-latest"
        else:
            url = f"{config.MISTRAL_LOCAL_URL.rstrip('/')}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            model = config.MISTRAL_LOCAL_MODEL or "mistral:latest"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"} if config.MISTRAL_API_KEY else None
        }

        # 25s timeout for local endpoint so it doesn't hang the orchestrator indefinitely
        resp = requests.post(url, json=payload, headers=headers, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            text_content = data["choices"][0]["message"]["content"]
            return cls._clean_json_response(text_content)
        else:
            error_msg = f"Mistral endpoint error (Status {resp.status_code}): {resp.text[:400]}"
            logger.error(error_msg)
            raise Exception(error_msg)
