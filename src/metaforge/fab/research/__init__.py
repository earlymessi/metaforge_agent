"""FAB research-lab solvers (isolated from APS generic catalog)."""

from metaforge.fab.research.methods import list_methods
from metaforge.fab.research.solve import run_research_compare, run_research_solve

__all__ = ["list_methods", "run_research_solve", "run_research_compare"]
