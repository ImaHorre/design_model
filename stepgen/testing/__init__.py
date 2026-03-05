"""
stepgen.testing
===============
Comprehensive testing framework for experimental validation of droplet generation models.

This module provides systematic testing and analysis tools for comparing model predictions
against experimental data, with focus on duty factor analysis, time-state model evaluation,
and performance optimization.
"""

from .experimental_test_suite import ExperimentalTestSuite
from .duty_factor_analyzer import DutyFactorAnalyzer
from .time_state_evaluator import TimeStateEvaluator
from .pcap_verifier import PcapVerifier

__all__ = [
    "ExperimentalTestSuite",
    "DutyFactorAnalyzer",
    "TimeStateEvaluator",
    "PcapVerifier",
]