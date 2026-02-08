"""
LLM Router - Multi-Provider LLM Integration
=================================================

Supports 14+ models across 7 providers:
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude 3.5 Sonnet, Haiku)
- Google (Gemini 2.5 Flash/Pro)
- Groq (Llama 3.1/3.3)
- xAI (Grok)
- GLM (GLM-4.7)
- HuggingFace (open-source models)

Usage:
    from mat.llm_router import LLMRouter, LLMMessage, LLMResponse

    router = LLMRouter()
    response = await router.call(
        messages=[{"role": "user", "content": "Hello!"}],
        model="gpt-4o"  # or None for auto-selection
    )
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from collections import defaultdict

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class LLMProvider(Enum):
    """LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROQ = "groq"
    XAI = "xai"
    GLM = "glm"
    HUGGINGFACE = "huggingface"
    CEREBRAS = "cerebras"


class TaskType(Enum):
    """Task types for model selection"""
    CODE_GENERATION = "code_generation"     # Builder: fast models
    CODE_ANALYSIS = "code_analysis"        # Skeptic: thorough models
    CODE_REVIEW = "code_review"           # Auditor: balanced
    GENERAL = "general"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class LLMMessage:
    """Message for LLM"""
    role: str  # system, user, assistant
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Response from LLM"""
    content: str
    provider: LLMProvider
    model: str
    tokens_used: Dict[str, int] = field(default_factory=dict)
    cost: float = 0.0
    latency: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "provider": self.provider.value if isinstance(self.provider, LLMProvider) else self.provider,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
            "latency": self.latency,
            "timestamp": self.timestamp
        }


@dataclass
class ModelConfig:
    """Model configuration"""
    provider: LLMProvider
    model_name: str
    api_key_env: str
    base_url: Optional[str] = None
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    max_tokens: int = 4000
    timeout: int = 60
    quality_score: float = 0.8
    speed_score: float = 0.8


# =============================================================================
# MODEL CONFIGURATIONS
# =============================================================================

PRECONFIGURED_MODELS: Dict[str, ModelConfig] = {
    # OpenAI
    "gpt-4o": ModelConfig(
        provider=LLMProvider.OPENAI,
        model_name="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        cost_per_1m_input=2.50,
        cost_per_1m_output=10.00,
        max_tokens=128000,
        quality_score=0.95,
        speed_score=0.85
    ),
    "gpt-4o-mini": ModelConfig(
        provider=LLMProvider.OPENAI,
        model_name="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        cost_per_1m_input=0.15,
        cost_per_1m_output=0.60,
        max_tokens=128000,
        quality_score=0.80,
        speed_score=0.95
    ),

    # Anthropic
    "claude-3.5-sonnet": ModelConfig(
        provider=LLMProvider.ANTHROPIC,
        model_name="claude-3.5-sonnet",
        api_key_env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com/v1/messages",
        cost_per_1m_input=3.00,
        cost_per_1m_output=15.00,
        max_tokens=200000,
        quality_score=0.96,
        speed_score=0.80
    ),
    "claude-3-haiku": ModelConfig(
        provider=LLMProvider.ANTHROPIC,
        model_name="claude-3-haiku",
        api_key_env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com/v1/messages",
        cost_per_1m_input=0.25,
        cost_per_1m_output=1.25,
        max_tokens=200000,
        quality_score=0.75,
        speed_score=0.98
    ),

    # Google
    "gemini-2.5-flash": ModelConfig(
        provider=LLMProvider.GOOGLE,
        model_name="gemini-2.5-flash",
        api_key_env="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        cost_per_1m_input=0.075,
        cost_per_1m_output=0.30,
        max_tokens=1000000,
        quality_score=0.85,
        speed_score=0.92
    ),
    "gemini-2.5-pro": ModelConfig(
        provider=LLMProvider.GOOGLE,
        model_name="gemini-2.5-pro",
        api_key_env="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        cost_per_1m_input=1.25,
        cost_per_1m_output=5.00,
        max_tokens=1000000,
        quality_score=0.90,
        speed_score=0.75
    ),

    # Groq (Llama 3.x - fast and free/cheap)
    "llama-3.1-8b-instant": ModelConfig(
        provider=LLMProvider.GROQ,
        model_name="llama-3.1-8b-instant",
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        max_tokens=128000,
        quality_score=0.70,
        speed_score=0.99
    ),
    "llama-3.3-70b-versatile": ModelConfig(
        provider=LLMProvider.GROQ,
        model_name="llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        cost_per_1m_input=0.59,
        cost_per_1m_output=0.79,
        max_tokens=128000,
        quality_score=0.88,
        speed_score=0.85
    ),

    # xAI (Grok)
    "grok-beta": ModelConfig(
        provider=LLMProvider.XAI,
        model_name="grok-beta",
        api_key_env="XAI_API_KEY",
        base_url="https://api.x.ai/v1",
        cost_per_1m_input=0.50,
        cost_per_1m_output=2.00,
        max_tokens=131072,
        quality_score=0.90,
        speed_score=0.88
    ),

    # GLM
    "glm-4.7": ModelConfig(
        provider=LLMProvider.GLM,
        model_name="glm-4.7",
        api_key_env="GLM_API_KEY",
        base_url="https://api.z.ai/api/anthropic",
        cost_per_1m_input=0.50,
        cost_per_1m_output=2.00,
        max_tokens=128000,
        quality_score=0.85,
        speed_score=0.85
    ),

    # HuggingFace (free tier)
    "hf-phi-3": ModelConfig(
        provider=LLMProvider.HUGGINGFACE,
        model_name="microsoft/Phi-3-mini-4k-instruct",
        api_key_env="HUGGINGFACE_API_KEY",
        base_url="https://api-inference.huggingface.co/v1",
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        max_tokens=4000,
        quality_score=0.72,
        speed_score=0.95
    ),
    "hf-mistral-7b": ModelConfig(
        provider=LLMProvider.HUGGINGFACE,
        model_name="mistralai/Mistral-7B-Instruct-v0.3",
        api_key_env="HUGGINGFACE_API_KEY",
        base_url="https://api-inference.huggingface.co/v1",
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        max_tokens=6000,
        quality_score=0.78,
        speed_score=0.80
    ),

    # Cerebras (ultra-fast)
    "cerebras-llama-3.1-8b": ModelConfig(
        provider=LLMProvider.CEREBRAS,
        model_name="llama-3.1-8b",
        api_key_env="CEREBRAS_API_KEY",
        base_url="https://api.cerebras.ai/v1",
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        max_tokens=128000,
        quality_score=0.72,
        speed_score=0.98
    ),
}


# =============================================================================
# LLM ROUTER
# =============================================================================

class LLMRouter:
    """
    LLM Router with multi-provider support

    Features:
    - 14+ models across 7 providers
    - Automatic model selection by task type
    - Fallback logic on errors
    - Cost tracking
    - Simple API
    """

    def __init__(
        self,
        quality_preference: str = "balanced",  # speed, balanced, quality
        preferred_models: Optional[List[str]] = None,
        enable_fallback: bool = True
    ):
        self.quality_preference = quality_preference
        self.preferred_models = preferred_models or []
        self.enable_fallback = enable_fallback

        # Load API keys
        self.api_keys: Dict[str, str] = {}
        self._load_api_keys()

        # Statistics
        self.stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "by_model": defaultdict(lambda: {"requests": 0, "tokens": 0, "cost": 0.0}),
            "by_provider": defaultdict(lambda: {"requests": 0, "tokens": 0, "cost": 0.0})
        }

        logger.info(f"[LLMRouter] Initialized with {len(self.api_keys)} API keys")

    def _load_api_keys(self) -> Dict[str, str]:
        """Load API keys from environment"""
        keys = {}
        for model_id, config in PRECONFIGURED_MODELS.items():
            key = os.getenv(config.api_key_env)
            if key:
                keys[model_id] = key
                logger.debug(f"[LLMRouter] Loaded key for {model_id}")
            else:
                logger.debug(f"[LLMRouter] No key for {model_id} ({config.api_key_env})")
        return keys

    def get_available_models(self, min_quality: float = 0.0) -> List[str]:
        """Get list of available models with API keys"""
        available = []
        for model_id, config in PRECONFIGURED_MODELS.items():
            if model_id in self.api_keys and config.quality_score >= min_quality:
                available.append(model_id)
        return sorted(available, key=lambda m: PRECONFIGURED_MODELS[m].quality_score, reverse=True)

    def select_model(
        self,
        task_type: TaskType = TaskType.GENERAL,
        quality_preference: Optional[str] = None
    ) -> str:
        """
        Select best model for task

        Args:
            task_type: Type of task
            quality_preference: Preference (speed/balanced/quality)

        Returns:
            Model identifier
        """
        quality = quality_preference or self.quality_preference

        # Get available models
        available = self.get_available_models()
        if not available:
            logger.warning("[LLMRouter] No models with API keys!")
            return "gpt-4o"  # Default fallback

        # If preferred models available and in available list, use them
        for pref in self.preferred_models:
            if pref in available:
                return pref

        # Select by task type and quality preference
        if task_type == TaskType.CODE_GENERATION:
            # Builder: prioritize speed
            if quality == "speed":
                return min(available, key=lambda m: PRECONFIGURED_MODELS[m].speed_score, reverse=True)
            else:
                return min(available, key=lambda m: (
                    PRECONFIGURED_MODELS[m].quality_score * 0.4 +
                    PRECONFIGURED_MODELS[m].speed_score * 0.6
                ), reverse=True)

        elif task_type == TaskType.CODE_ANALYSIS:
            # Skeptic: prioritize quality
            if quality == "speed":
                return min(available, key=lambda m: (
                    PRECONFIGURED_MODELS[m].quality_score * 0.6 +
                    PRECONFIGURED_MODELS[m].speed_score * 0.4
                ), reverse=True)
            else:
                return max(available, key=lambda m: PRECONFIGURED_MODELS[m].quality_score)

        else:  # GENERAL, CODE_REVIEW
            if quality == "speed":
                return min(available, key=lambda m: PRECONFIGURED_MODELS[m].speed_score, reverse=True)
            elif quality == "quality":
                return max(available, key=lambda m: PRECONFIGURED_MODELS[m].quality_score)
            else:  # balanced
                return max(available, key=lambda m: (
                    PRECONFIGURED_MODELS[m].quality_score * 0.5 +
                    PRECONFIGURED_MODELS[m].speed_score * 0.5
                ), reverse=True)

    async def call(
        self,
        messages: List[Union[LLMMessage, Dict[str, str]]],
        model: Optional[str] = None,
        task_type: TaskType = TaskType.GENERAL,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """
        Call LLM API

        Args:
            messages: List of messages
            model: Model identifier (auto-select if None)
            task_type: Type of task (for auto-selection)
            temperature: Generation temperature
            max_tokens: Max tokens to generate

        Returns:
            LLMResponse
        """
        start_time = time.time()

        # Normalize messages
        normalized = []
        for msg in messages:
            if isinstance(msg, LLMMessage):
                normalized.append({"role": msg.role, "content": msg.content})
            else:
                normalized.append(msg)

        # Select model
        if model is None:
            model = self.select_model(task_type)

        # Get config
        if model not in PRECONFIGURED_MODELS:
            return LLMResponse(
                content=f"Error: Unknown model {model}",
                provider=LLMProvider.OPENAI,
                model="unknown",
                latency=time.time() - start_time
            )

        config = PRECONFIGURED_MODELS[model]

        # Check API key
        if model not in self.api_keys:
            # Try fallback
            if self.enable_fallback:
                return await self._try_fallback(
                    normalized, model, task_type, temperature, max_tokens
                )
            return LLMResponse(
                content=f"Error: No API key for {model}",
                provider=config.provider,
                model=model,
                latency=time.time() - start_time
            )

        # Call provider
        try:
            result = await self._call_provider(
                config, self.api_keys[model], normalized, temperature, max_tokens
            )

            if "error" in result:
                if self.enable_fallback:
                    return await self._try_fallback(
                        normalized, model, task_type, temperature, max_tokens
                    )
                return LLMResponse(
                    content=result["error"],
                    provider=config.provider,
                    model=model,
                    latency=time.time() - start_time
                )

            # Build response
            latency = time.time() - start_time
            usage = result.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            cost = (
                (input_tokens / 1_000_000) * config.cost_per_1m_input +
                (output_tokens / 1_000_000) * config.cost_per_1m_output
            )

            response = LLMResponse(
                content=result.get("content", ""),
                provider=config.provider,
                model=model,
                tokens_used={
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": total_tokens
                },
                cost=cost,
                latency=latency
            )

            # Update stats
            self._update_stats(response)

            return response

        except Exception as e:
            logger.error(f"[LLMRouter] Exception: {e}")
            if self.enable_fallback:
                return await self._try_fallback(
                    normalized, model, task_type, temperature, max_tokens
                )
            return LLMResponse(
                content=f"Error: {str(e)}",
                provider=config.provider,
                model=model,
                latency=time.time() - start_time
            )

    async def _try_fallback(
        self,
        messages: List[Dict],
        failed_model: str,
        task_type: TaskType,
        temperature: float,
        max_tokens: Optional[int]
    ) -> LLMResponse:
        """Try fallback models"""
        available = [
            m for m in self.get_available_models()
            if m != failed_model
        ]

        for fallback_model in available[:3]:  # Try up to 3 alternatives
            config = PRECONFIGURED_MODELS[fallback_model]
            if fallback_model not in self.api_keys:
                continue

            try:
                logger.info(f"[LLMRouter] Trying fallback: {fallback_model}")
                result = await self._call_provider(
                    config, self.api_keys[fallback_model],
                    messages, temperature, max_tokens
                )

                if "error" not in result:
                    logger.info(f"[LLMRouter] Fallback success: {fallback_model}")
                    start_time = time.time()
                    usage = result.get("usage", {})

                    return LLMResponse(
                        content=result.get("content", ""),
                        provider=config.provider,
                        model=fallback_model,
                        tokens_used=usage,
                        cost=0.0,
                        latency=time.time() - start_time,
                        metadata={"fallback_from": failed_model}
                    )

            except Exception as e:
                logger.warning(f"[LLMRouter] Fallback {fallback_model} failed: {e}")

        return LLMResponse(
            content="All models unavailable. Please check API keys.",
            provider=LLMProvider.OPENAI,
            model="fallback",
            cost=0.0,
            latency=0.0
        )

    async def _call_provider(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call specific provider"""
        provider = config.provider

        if provider == LLMProvider.OPENAI:
            return await self._call_openai(config, api_key, messages, temperature, max_tokens)
        elif provider == LLMProvider.ANTHROPIC:
            return await self._call_anthropic(config, api_key, messages, temperature, max_tokens)
        elif provider == LLMProvider.GOOGLE:
            return await self._call_google(config, api_key, messages, temperature, max_tokens)
        elif provider == LLMProvider.GROQ:
            return await self._call_groq(config, api_key, messages, temperature, max_tokens)
        elif provider == LLMProvider.XAI:
            return await self._call_xai(config, api_key, messages, temperature, max_tokens)
        elif provider == LLMProvider.GLM:
            return await self._call_glm(config, api_key, messages, temperature, max_tokens)
        elif provider == LLMProvider.HUGGINGFACE:
            return await self._call_huggingface(config, api_key, messages, temperature, max_tokens)
        elif provider == LLMProvider.CEREBRAS:
            return await self._call_cerebras(config, api_key, messages, temperature, max_tokens)
        else:
            return {"error": f"Unknown provider: {provider}"}

    async def _call_openai(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call OpenAI API"""
        import aiohttp

        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or config.max_tokens
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}

                data = await resp.json()

                return {
                    "content": data["choices"][0]["message"]["content"],
                    "usage": {
                        "prompt_tokens": data["usage"]["prompt_tokens"],
                        "completion_tokens": data["usage"]["completion_tokens"],
                        "total_tokens": data["usage"]["total_tokens"]
                    }
                }

    async def _call_anthropic(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call Anthropic API"""
        import aiohttp

        url = f"{config.base_url}"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model_name,
            "messages": messages,
            "max_tokens": max_tokens or config.max_tokens,
            "temperature": temperature
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"error": f"HTTP {resp.status}: {text[:200]}"}

                data = await resp.json()

                return {
                    "content": data["content"][0]["text"],
                    "usage": {
                        "prompt_tokens": data["usage"]["input_tokens"],
                        "completion_tokens": data["usage"]["output_tokens"],
                        "total_tokens": data["usage"]["input_tokens"] + data["usage"]["output_tokens"]
                    }
                }

    async def _call_google(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call Google API"""
        import aiohttp

        # Convert messages to Gemini format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        url = f"{config.base_url}:generateContent?key={api_key}"
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens or config.max_tokens
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=config.timeout) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}

                data = await resp.json()

                content = data["candidates"][0]["content"]["parts"][0]["text"]
                usage = data.get("usageMetadata", {})

                return {
                    "content": content,
                    "usage": {
                        "prompt_tokens": usage.get("promptTokenCount", 0),
                        "completion_tokens": usage.get("candidatesTokenCount", 0),
                        "total_tokens": usage.get("totalTokenCount", 0)
                    }
                }

    async def _call_groq(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call Groq API"""
        import aiohttp

        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or config.max_tokens
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}

                data = await resp.json()

                return {
                    "content": data["choices"][0]["message"]["content"],
                    "usage": {
                        "prompt_tokens": data["usage"]["prompt_tokens"],
                        "completion_tokens": data["usage"]["completion_tokens"],
                        "total_tokens": data["usage"]["total_tokens"]
                    }
                }

    async def _call_xai(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call xAI (Grok) API"""
        import aiohttp

        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or config.max_tokens
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}

                data = await resp.json()

                return {
                    "content": data["choices"][0]["message"]["content"],
                    "usage": {
                        "prompt_tokens": data["usage"]["prompt_tokens"],
                        "completion_tokens": data["usage"]["completion_tokens"],
                        "total_tokens": data["usage"]["total_tokens"]
                    }
                }

    async def _call_glm(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call GLM API (Anthropic-compatible)"""
        import aiohttp

        # Find system and last user message
        system_msg = None
        last_user = None
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            elif msg["role"] == "user" and last_user is None:
                last_user = msg["content"]

        url = f"{config.base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model_name,
            "max_tokens": max_tokens or config.max_tokens,
            "system": system_msg or "You are a helpful AI assistant.",
            "messages": [{"role": "user", "content": last_user or "Hello"}],
            "temperature": temperature
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {"error": f"HTTP {resp.status}: {text[:200]}"}

                data = await resp.json()

                return {
                    "content": data.get("content", [{}])[0].get("text", ""),
                    "usage": {
                        "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                        "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                        "total_tokens": 0
                    }
                }

    async def _call_huggingface(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call HuggingFace Inference API"""
        import aiohttp

        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or config.max_tokens,
            "stream": False
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as resp:
                if resp.status == 503:
                    # Model loading
                    await asyncio.sleep(2)
                    async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as resp2:
                        if resp2.status != 200:
                            return {"error": f"HTTP {resp2.status}"}
                        data = await resp2.json()
                elif resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}

                data = await resp.json()

                return {
                    "content": data["choices"][0]["message"]["content"],
                    "usage": data.get("usage", {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    })
                }

    async def _call_cerebras(
        self,
        config: ModelConfig,
        api_key: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """Call Cerebras Inference API"""
        import aiohttp

        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or config.max_tokens,
            "stream": False
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}

                data = await resp.json()

                return {
                    "content": data["choices"][0]["message"]["content"],
                    "usage": data.get("usage", {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    })
                }

    def _update_stats(self, response: LLMResponse):
        """Update usage statistics"""
        self.stats["total_requests"] += 1
        self.stats["total_tokens"] += response.tokens_used.get("total", 0)
        self.stats["total_cost"] += response.cost

        # By model
        model = response.model
        self.stats["by_model"][model]["requests"] += 1
        self.stats["by_model"][model]["tokens"] += response.tokens_used.get("total", 0)
        self.stats["by_model"][model]["cost"] += response.cost

        # By provider
        provider = response.provider.value if isinstance(response.provider, LLMProvider) else response.provider
        self.stats["by_provider"][provider]["requests"] += 1
        self.stats["by_provider"][provider]["tokens"] += response.tokens_used.get("total", 0)
        self.stats["by_provider"][provider]["cost"] += response.cost

    def get_statistics(self) -> Dict[str, Any]:
        """Get usage statistics"""
        return dict(self.stats)


# =============================================================================
# SINGLETON
# =============================================================================

_global_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """Get global LLMRouter instance"""
    global _global_router
    if _global_router is None:
        _global_router = LLMRouter()
    return _global_router


__all__ = [
    # Enums
    "LLMProvider",
    "TaskType",

    # Classes
    "LLMRouter",
    "LLMMessage",
    "LLMResponse",
    "ModelConfig",
    "PRECONFIGURED_MODELS",

    # Functions
    "get_router",
]
