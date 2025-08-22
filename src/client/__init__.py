"""
Client module for the data scientist project.

This module provides functionality for setting up LLM configurations
and working with code agents.
"""

from .agent import CustomAgent, StepController, SmartContextManager, agent_runner, toggle_manual_mode, next_step
from .telemetry import TelemetryManager
from . import ui
from .agent_router import TherapyRouter

__all__ = [
    'CustomAgent',
    'StepController',
    'SmartContextManager',
    'agent_runner',
    'toggle_manual_mode',
    'next_step',
    'TelemetryManager',
    'ui',
    'TherapyRouter',

]
