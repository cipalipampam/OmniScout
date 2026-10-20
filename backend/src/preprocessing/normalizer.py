
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# parents[0] = preprocessing, parents[1] = src, parents[2] = backend (apps/backend)
_DEFAULT_DICT_PATH = Path(__file__).resolve().parents[2] / "storage" / "dictionaries" / "kamusalay.csv"



def load_slang_dictionary(path=None) -> dict:
    """Muat kamus slang dari CSV tanpa header (kolom 0 = slang, kolom 1 = baku) menjadi {slang: baku}."""
    # Resolusi path
    if path is None:
        try:
            from configs.config import KAMUSALAY_PATH
            resolved_path = Path(KAMUSALAY_PATH)
        except ImportError:
            resolved_path = _DEFAULT_DICT_PATH
    else:
        resolved_path = Path(path)

    if not resolved_path.exists():
        logger.error(f"File kamus tidak ditemukan: {resolved_path}")
        return {}

    try:
        df = pd.read_csv(
            resolved_path,
            header=None,
            encoding="latin-1",
            on_bad_lines="skip",
            dtype=str,
        )
        # Bersihkan kolom: strip whitespace, lowercase
        col_slang = df[0].str.strip().str.lower()
        col_baku  = df[1].str.strip().str.lower()

        # Buat dictionary hanya dari pasangan yang valid (keduanya non-NaN & non-kosong)
        mask = col_slang.notna() & col_baku.notna() & (col_slang != "") & (col_baku != "")
        slang_dict = dict(zip(col_slang[mask], col_baku[mask]))

        logger.info(f"Kamus slang berhasil dimuat: {len(slang_dict):,} entri dari '{resolved_path.name}'.")
        return slang_dict
    except Exception as e:
        logger.error(f"Gagal memuat kamus slang dari '{resolved_path}': {e}")
        return {}


# Class SlangNormalizer

class SlangNormalizer:
    """Normalisasi slang → kata baku dengan lookup O(1) pada hash map in-memory."""

    def __init__(self, dictionary_path=None):
        """Muat kamus ke memori; dictionary_path None memakai path default dari config."""
        self.dictionary: dict = load_slang_dictionary(dictionary_path)
        self.dictionary_size: int = len(self.dictionary)

    def normalize(self, text: str) -> str:
        """Ganti tiap token slang dengan padanan baku (split → lookup → join)."""
        if not isinstance(text, str) or not text.strip():
            return ""

        if not self.dictionary:
            return text

        tokens = text.split()
        normalized_tokens = [
            self.dictionary.get(token.lower(), token)
            for token in tokens
        ]
        return " ".join(normalized_tokens)

    def __repr__(self) -> str:
        return f"SlangNormalizer(dictionary_size={self.dictionary_size:,})"
