
import re
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Regex Pattern — Dikompilasi sekali untuk efisiensi

# 1. URL lengkap: http, https, ftp, www, dan shortlink t.co
_RE_URL = re.compile(
    r"(?:https?://|ftp://|www\.)\S+|t\.co/\S+",
    re.IGNORECASE,
)

# 2. Mention — hapus tanda '@' saja, pertahankan username
_RE_MENTION_SYMBOL = re.compile(r"@(?=\S)")

# 3. Hashtag — hapus tanda '#' saja, pertahankan kata
_RE_HASHTAG_SYMBOL = re.compile(r"#(?=\S)")

# 4. Prefix RT (Retweet) di awal kalimat
_RE_RT_PREFIX = re.compile(r"^\s*RT\s*:?\s*", re.IGNORECASE)

# 5. Hapus karakter non-alfanumerik & non-spasi (emoji, simbol, tanda baca, dll.)
#    Pertahankan huruf Latin (a-z A-Z), angka, dan spasi.
_RE_NON_ALPHANUM = re.compile(r"[^a-zA-Z0-9\s]")

# 6. Normalisasi multiple whitespace
_RE_MULTI_SPACE = re.compile(r"\s+")



def clean_text(text: str) -> str:
    """Bersihkan satu teks mentah media sosial sesuai 6 tahap di bawah."""
    if not isinstance(text, str):
        return ""

    # 1. Hapus URL
    text = _RE_URL.sub(" ", text)

    # 2. Hapus simbol @ — pertahankan nama username
    text = _RE_MENTION_SYMBOL.sub("", text)

    # 3. Hapus simbol # — pertahankan kata hashtag
    text = _RE_HASHTAG_SYMBOL.sub("", text)

    # 4. Hapus prefix RT (Retweet)
    text = _RE_RT_PREFIX.sub("", text)

    # 5. Hapus karakter non-alfanumerik (emoji, simbol, tanda baca, dst.)
    text = _RE_NON_ALPHANUM.sub(" ", text)

    # 6. Normalisasi spasi
    text = _RE_MULTI_SPACE.sub(" ", text).strip()

    return text


def case_folding(text: str) -> str:
    """Ubah seluruh huruf menjadi lowercase (case folding)."""
    if not isinstance(text, str):
        return ""
    return text.lower()


def remove_duplicates(df: pd.DataFrame, subset=None) -> pd.DataFrame:
    """Hapus baris duplikat pada kolom `subset` (default ['user_id', 'content']), keep='first'."""
    if df.empty:
        return df

    if subset is None:
        subset = ["user_id", "content"]

    # Hanya gunakan kolom subset yang benar-benar ada di DataFrame
    valid_subset = [col for col in subset if col in df.columns]
    if not valid_subset:
        logger.warning(
            "remove_duplicates: Tidak ada kolom subset yang valid di DataFrame. "
            "Melewati proses deduplikasi."
        )
        return df

    before = len(df)
    df = df.drop_duplicates(subset=valid_subset, keep="first").reset_index(drop=True)
    after = len(df)

    if before != after:
        logger.info(f"Deduplikasi: {before - after} baris duplikat dihapus ({before} → {after}).")

    return df
