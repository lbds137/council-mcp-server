"""Model manager for handling dual-model configuration with fallback."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Tuple

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

logger = logging.getLogger(__name__)


class DualModelManager:
    """Manages primary and fallback Gemini models with automatic failover."""

    def __init__(self, api_key: str):
        """Initialize the model manager with API key and model configuration."""
        genai.configure(api_key=api_key)

        # Get model names from environment or use defaults
        self.primary_model_name = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.0-flash-exp")
        self.fallback_model_name = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-1.5-pro")

        # Timeout configuration (in seconds)
        self.timeout = float(os.getenv("GEMINI_MODEL_TIMEOUT", "10000")) / 1000

        # Initialize models
        self._primary_model = self._initialize_model(self.primary_model_name, "Primary")
        self._fallback_model = self._initialize_model(self.fallback_model_name, "Fallback")

        # Track model usage
        self.primary_calls = 0
        self.fallback_calls = 0
        self.primary_failures = 0

    def _initialize_model(self, model_name: str, model_type: str):
        """Initialize a single model with error handling."""
        try:
            model = genai.GenerativeModel(model_name)
            logger.info(f"{model_type} model initialized: {model_name}")
            return model
        except Exception as e:
            logger.error(f"Failed to initialize {model_type} model {model_name}: {e}")
            return None

    def _generate_with_timeout(self, model, model_name: str, prompt: str, timeout: float) -> str:
        """Execute model generation with timeout using ThreadPoolExecutor."""
        from google.generativeai.types import RequestOptions

        # Create request options with timeout
        request_options = RequestOptions(timeout=timeout)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                model.generate_content, prompt, request_options=request_options
            )
            try:
                response = future.result(timeout=timeout)
                return response.text
            except FutureTimeoutError:
                logger.warning(f"{model_name} timed out after {timeout}s")
                future.cancel()
                raise TimeoutError(f"{model_name} generation timed out")

    def generate_content(self, prompt: str) -> Tuple[str, str]:
        """
        Generate content using primary model with automatic fallback.

        Returns:
            Tuple of (response_text, model_used)
        """
        # Try primary model first
        if self._primary_model:
            try:
                self.primary_calls += 1
                response_text = self._generate_with_timeout(
                    self._primary_model, self.primary_model_name, prompt, self.timeout
                )
                logger.debug("Primary model responded successfully")
                return response_text, self.primary_model_name
            except (
                google_exceptions.GoogleAPICallError,
                google_exceptions.InternalServerError,
                ValueError,
                TimeoutError,
                Exception,
            ) as e:
                self.primary_failures += 1
                error_type = type(e).__name__
                logger.warning(
                    f"Primary model failed (attempt {self.primary_failures}): {error_type}: {e}"
                )
                if hasattr(e, "code"):
                    logger.warning(f"Error code: {e.code}")
                if hasattr(e, "details"):
                    logger.warning(f"Error details: {e.details}")
                # Check for 500 errors specifically
                if "500" in str(e) or "Internal" in str(e):
                    logger.warning(
                        "Detected 500/Internal error - typically a temporary Gemini API issue"
                    )

        # Fallback to secondary model
        if self._fallback_model:
            try:
                self.fallback_calls += 1
                response_text = self._generate_with_timeout(
                    self._fallback_model,
                    self.fallback_model_name,
                    prompt,
                    self.timeout * 1.5,  # Give fallback more time
                )
                logger.info("Fallback model responded successfully")
                return response_text, self.fallback_model_name
            except Exception as e:
                error_type = type(e).__name__
                logger.error(f"Fallback model also failed: {error_type}: {e}")
                if hasattr(e, "code"):
                    logger.error(f"Error code: {e.code}")
                if hasattr(e, "details"):
                    logger.error(f"Error details: {e.details}")
                raise RuntimeError(f"Both models failed. Last error: {error_type}: {e}")

        raise RuntimeError("No models available for content generation")

    def get_stats(self) -> dict:
        """Get usage statistics for the model manager."""
        total_calls = self.primary_calls + self.fallback_calls
        primary_success_rate = (
            (self.primary_calls - self.primary_failures) / self.primary_calls
            if self.primary_calls > 0
            else 0
        )

        return {
            "primary_model": self.primary_model_name,
            "fallback_model": self.fallback_model_name,
            "total_calls": total_calls,
            "primary_calls": self.primary_calls,
            "fallback_calls": self.fallback_calls,
            "primary_failures": self.primary_failures,
            "primary_success_rate": primary_success_rate,
            "timeout_seconds": self.timeout,
        }
