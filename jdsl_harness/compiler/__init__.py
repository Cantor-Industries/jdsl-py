"""The jdsl behavior compiler: normalize → mine → consolidate → staticize →
residualize → verify → package (design §14, §17, §24, §35 PR8-PR13).

Deterministic by construction; the compiler model only proposes hypotheses that
recorded evidence and replay must confirm (§24.1, §53 principle 3).
"""

from jdsl_harness.compiler.candidates import Fact, extract_facts
from jdsl_harness.compiler.consolidate import Candidate, Evidence, consolidate
from jdsl_harness.compiler.lineage import find_source, is_meaningful
from jdsl_harness.compiler.model import (
    CompilerModel,
    HeuristicCompilerModel,
    LLMCompilerModel,
)
from jdsl_harness.compiler.normalize import (
    NormEpisode,
    NormStep,
    normalize_all,
    normalize_episode,
)
from jdsl_harness.compiler.package import CompileResult, build_package, compile_behavior
from jdsl_harness.compiler.staticize import CompiledBehavior, staticize
from jdsl_harness.compiler.verify import VerificationReport, verify

__all__ = [
    "find_source",
    "is_meaningful",
    "normalize_episode",
    "normalize_all",
    "NormEpisode",
    "NormStep",
    "extract_facts",
    "Fact",
    "consolidate",
    "Candidate",
    "Evidence",
    "staticize",
    "CompiledBehavior",
    "verify",
    "VerificationReport",
    "compile_behavior",
    "CompileResult",
    "build_package",
    "CompilerModel",
    "HeuristicCompilerModel",
    "LLMCompilerModel",
]
