"""Taxonomy Agent; Loops over all description files and uses tools to store information in a structured format for later retrieval."""

from pathlib import Path
import ollama
from .fetch import CLIENT, MODEL


def taxonomy_system() -> str:
    return """
# Taxonomy Manager


"""
