"""Agents – autonomous legal-AI task runners."""

from agents.base_agent import AgentRun, BaseAgent
from agents.fraud_detection_agent import (
    FraudAnalysisResult,
    FraudDetectionAgent,
    FraudIndicator,
)
from agents.research_agent import CaseResearchAgent, ResearchResult
from agents.summarization_agent import SummarizationAgent, SummarizationResult

__all__ = [
    "AgentRun",
    "BaseAgent",
    "CaseResearchAgent",
    "FraudAnalysisResult",
    "FraudDetectionAgent",
    "FraudIndicator",
    "ResearchResult",
    "SummarizationAgent",
    "SummarizationResult",
]
