
# CATATAN ARSITEKTUR (dihapus 2026-09-25):
# Barrel re-export `__all__` (26 nama schema) yang dulu ada di file ini DIHAPUS karena
# dead code — tidak ada satu pun modul yang mengimpor `from app.schemas import ...`.
# Seluruh pemakai sudah mengimpor langsung dari modul subdomainnya, mis.:
#     from app.schemas.auth_schema import AllSessionsStatusResponse
#     from app.schemas.scraper_schema import ScrapeRequest
#     from app.schemas.scrape_schema import ScrapeRunRequest
# Impor langsung seperti ini juga menghindari memuat 26 schema sekaligus dan
# mencegah nama modul tertutup (shadowed) oleh nama kelas saat refactor berikutnya.

__all__: list[str] = []
