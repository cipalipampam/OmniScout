
import asyncio
import logging
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# Pastikan direktori backend ada di sys.path agar bisa import configs
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from configs.config import X_PROFILE_DIR
from src.scraping.base_scraper import create_browser
from src.utils.async_compat import ensure_proactor_loop

logger = logging.getLogger("login_x")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


LOGIN_URL       = "https://x.com/i/flow/login"
MAX_WAIT_SEC    = 600       # Maks 10 menit (120 polling x 5 detik)
POLL_INTERVAL   = 5         # Interval cek sesi (detik)

# Selektor DOM antarmuka akun X yang terotentikasi
LOGGED_IN_SELECTORS = [
    '[data-testid="SideNav_AccountSwitcher_Button"]',
    '[data-testid="AppTabBar_Profile_Link"]',
    '[data-testid="SideNav_NewTweet_Button"]',
]

# `STEALTH_ARGS` / `STEALTH_SCRIPT` + factory browser lokal DIHAPUS (2026-09-25):
# sekarang memakai `create_browser()` dari `src/scraping/base_scraper.py` — satu
# implementasi untuk scraping & login (diimpor di blok import di atas).



@ensure_proactor_loop
async def setup_x_login(profile_dir: str = None) -> bool:
    """Buka browser GUI, polling login maks 10 menit, simpan sesi permanen.

    Kembalikan True bila login terdeteksi, False bila timeout/gagal.
    """
    if profile_dir is None:
        profile_dir = str(X_PROFILE_DIR)

    # Pastikan direktori profil ada
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("  X / TWITTER LOGIN SETUP")
    logger.info(f"  Profile Directory: {profile_dir}")
    logger.info("=" * 60)

    async with async_playwright() as p:
        try:
            context, page = await create_browser(p, profile_dir=profile_dir, headless=False)
        except RuntimeError as e:
            logger.error(str(e))
            return False

        try:
            logger.info(f"Membuka halaman login: {LOGIN_URL}")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)

            print("\n" + "=" * 65)
            print("  SILAKAN LOGIN KE AKUN X (TWITTER) ANDA PADA BROWSER YANG TERBUKA.")
            print("  Masukkan username, password, dan selesaikan 2FA/CAPTCHA jika ada.")
            print("  Script akan otomatis mendeteksi ketika login berhasil.")
            print("  Sesi akan tersimpan otomatis setelah login berhasil.")
            print("=" * 65 + "\n")

            max_checks   = MAX_WAIT_SEC // POLL_INTERVAL
            logged_in    = False

            for check in range(1, max_checks + 1):
                await asyncio.sleep(POLL_INTERVAL)

                if page.is_closed():
                    logger.info("Tab browser ditutup oleh pengguna.")
                    try:
                        cookies = await context.cookies()
                        if any(
                            c.get("name") == "auth_token" and bool(c.get("value"))
                            for c in cookies
                        ):
                            logged_in = True
                    except Exception:
                        pass
                    break

                try:
                    cookies     = await context.cookies()
                    has_auth    = any(c.get("name") == "auth_token" and bool(c.get("value")) for c in cookies)
                    has_twid    = any(c.get("name") == "twid"       and bool(c.get("value")) for c in cookies)
                    current_url = page.url.lower()

                    if (has_auth or has_twid) and "/i/flow/login" not in current_url:
                        logged_in = True
                        logger.info("✓ Cookie auth_token / twid terdeteksi — login berhasil!")
                        break

                    for selector in LOGGED_IN_SELECTORS:
                        try:
                            if await page.locator(selector).count() > 0:
                                logged_in = True
                                logger.info(f"✓ Elemen DOM akun terdeteksi ({selector}) — login berhasil!")
                                break
                        except Exception:
                            pass

                    if logged_in:
                        break

                except Exception as check_err:
                    logger.debug(f"Polling sesi (check {check}): {check_err}")

                # Log progres setiap 30 detik
                if check % (30 // POLL_INTERVAL) == 0:
                    logger.info(f"Menunggu login... ({check * POLL_INTERVAL} detik berlalu dari maks {MAX_WAIT_SEC} detik)")

            if logged_in:
                await asyncio.sleep(3)  # Beri waktu agar data sesi penuh tersimpan ke disk
                print("\n" + "★" * 65)
                print(f"  SUKSES: LOGIN X BERHASIL!")
                print(f"  Sesi tersimpan di: {profile_dir}")
                print("  Anda sekarang dapat menjalankan scraper X.")
                print("★" * 65 + "\n")
            else:
                logger.warning("Login tidak terdeteksi dalam batas waktu maksimum.")
                logger.warning("Silakan jalankan kembali script ini dan selesaikan proses login.")

            return logged_in

        finally:
            try:
                await context.close()
            except Exception:
                pass



if __name__ == "__main__":
    # Izinkan override path profil via argumen CLI:
    # python src/auth/login_x.py [custom_profile_dir]
    profile = sys.argv[1] if len(sys.argv) > 1 else str(X_PROFILE_DIR)
    result  = asyncio.run(setup_x_login(profile))
    sys.exit(0 if result else 1)
