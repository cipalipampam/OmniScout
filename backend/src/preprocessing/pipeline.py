
import logging
import pandas as pd
from tqdm import tqdm

from .cleaner import remove_duplicates

logger = logging.getLogger(__name__)


def normalize_whitespace(text: str) -> str:
    """Pertahankan isi teks sambil merapikan whitespace untuk kebutuhan pencarian."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())


# Class PreprocessingPipeline

class PreprocessingPipeline:
    """Preprocessing wajib untuk data scraping: deduplikasi dan whitespace."""

    def transform_text(self, text: str) -> str:
        """Rapikan whitespace tanpa mengubah kata, URL, simbol, atau kapitalisasi."""
        return normalize_whitespace(text)

    def transform_batch(self, texts: list) -> list:
        """Preprocess daftar teks; urutan hasil sama dengan urutan input."""
        return [self.transform_text(text) for text in texts]

    def transform_dataframe(
        self,
        df: pd.DataFrame,
        text_column: str = "content",
        show_progress: bool = True,
    ) -> pd.DataFrame:
        """Deduplicate dan rapikan whitespace pada kolom teks asli."""
        if df.empty:
            logger.warning("transform_dataframe: DataFrame kosong, tidak ada yang diproses.")
            return df

        df = df.copy()

        # 1. Pastikan kolom teks ada
        if text_column not in df.columns:
            raise ValueError(
                f"transform_dataframe: Kolom '{text_column}' tidak ditemukan di DataFrame. "
                f"Kolom yang tersedia: {list(df.columns)}"
            )

        # 2. Rapikan whitespace sebelum deduplikasi agar variasi spasi tidak
        # menghasilkan baris yang secara isi sebenarnya sama.
        total = len(df)
        logger.info(f"Memulai preprocessing {total:,} baris teks (kolom: '{text_column}')...")

        if show_progress:
            tqdm.pandas(desc="  Preprocessing", unit="row", colour="cyan")
            cleaned_series = df[text_column].progress_apply(self.transform_text)
        else:
            cleaned_series = df[text_column].apply(self.transform_text)

        df[text_column] = cleaned_series

        # 3. Deduplikasi wajib setelah whitespace konsisten
        df = remove_duplicates(df)

        # 4. Hapus baris dengan teks kosong setelah preprocessing
        before_filter = len(df)
        df = df[df[text_column].str.strip() != ""].reset_index(drop=True)
        after_filter = len(df)

        if before_filter != after_filter:
            logger.info(
                f"Filter teks kosong: {before_filter - after_filter} baris dibuang "
                f"({before_filter} → {after_filter})."
            )

        # 5. Susun urutan kolom agar konsisten dengan standar
        standard_cols = ["platform", "source", "source_thread", "user_id", "type", "date", "content"]
        ordered_cols = [c for c in standard_cols if c in df.columns] + [
            c for c in df.columns if c not in standard_cols
        ]
        df = df[ordered_cols]

        logger.info(f"Preprocessing selesai. {after_filter:,} baris teks bersih dihasilkan.")
        return df

    def __repr__(self) -> str:
        return "PreprocessingPipeline(stages=['deduplication', 'whitespace'])"
