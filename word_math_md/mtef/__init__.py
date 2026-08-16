"""MathType MTEF (Equation Native) → LaTeX.

Adapted from AndyQsmart/MTEF-py (based on zhexiao/mtef-go).
OLE compound files are opened with olefile; only the Equation Native stream is parsed.
"""

from .mtef import MTEF, mtef_bytes_to_latex, ole_bytes_to_latex

__all__ = ["MTEF", "mtef_bytes_to_latex", "ole_bytes_to_latex"]
