"""Aurum voice synthesis package."""

from .config import PipelineConfig
from .intelligence import DomainIntelligenceService
from .pipeline import VoiceSynthesisPipeline
from .providers import ElevenLabsProvider
from .web import create_app

__all__ = [
    "PipelineConfig",
    "VoiceSynthesisPipeline",
    "ElevenLabsProvider",
    "DomainIntelligenceService",
    "create_app",
]
