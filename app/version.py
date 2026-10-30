"""
Versione dell'applicazione.
La fonte unica è `[project] version` in pyproject.toml, letto a runtime.
"""

import tomllib
from pathlib import Path


def get_version() -> str:
    """
    Legge la versione da pyproject.toml, risalendo le cartelle da questo file.

    Ritorna:
        La stringa di versione (es. "0.2.0"), oppure "unknown" se il file non
        si trova o non è leggibile. Non solleva mai: la versione non deve
        far crashare l'app.
    """
    try:
        for cartella in Path(__file__).resolve().parents:
            candidato = cartella / "pyproject.toml"
            if candidato.is_file():
                with open(candidato, "rb") as f:
                    return str(tomllib.load(f)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        pass
    return "unknown"
