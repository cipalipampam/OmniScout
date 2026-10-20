
import asyncio
import logging
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# Pastikan direktori backend ada di sys.path agar bisa import configs
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from configs.config import THREADS_PROFILE_DIR
from src.scraping.base_scraper import create_browser
from src.utils.async_compat import ensure_proactor_loop

logger = logging.getLogger("login_threads")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


LOGIN_URL       = "https://www.threads.com/login"
VERIFY_URL      = "https://www.threads.com/"
MAX_WAIT_SEC    = 600       # Maks 10 menit (120 polling x 5 detik)
POLL_INTERVAL   = 5         # Interval cek sesi (detik)

# Cookie primer autentikasi Threads / Instagram
AUTH_COOKIES = ("sessionid", "ds_user_id")

# Host domain tempat cookie autentikasi HARUS berlaku.
#
# Scraper membuka `threads.com`. Cookie `sessionid` yang hanya terbit untuk
# `.threads.net` / `.instagram.com` tidak dikirim ke `threads.com`, sehingga
# scraping berjalan sebagai tamu — Threads lalu membounce permalink ke beranda.
# Karena itu login dilakukan dan diverifikasi pada host `threads.com`.
AUTH_COOKIE_HOSTS = ("threads.com",)

# Selektor DOM ikon navigasi yang hanya muncul setelah akun login
LOGGED_IN_SELECTORS = [
    'svg[aria-label*="Create"]',    'svg[aria-label*="Buat"]',
    'svg[aria-label*="Activity"]',  'svg[aria-label*="Aktivitas"]',
    'svg[aria-label*="Profile"]',   'svg[aria-label*="Profil"]',
]

# `STEALTH_ARGS` / `STEALTH_SCRIPT` + factory browser lokal DIHAPUS (2026-09-25):
# sekarang memakai `create_browser()` dari `src/scraping/base_scraper.py` — satu
# implementasi untuk scraping & login (diimpor di blok import di atas).


def _host_is_allowed(hosts: list[str]) -> bool:
    """True bila minimal satu cookie auth berlaku untuk host threads.com."""
    return any(
        host and any(allowed in host for allowed in AUTH_COOKIE_HOSTS)
        for host in hosts
    )


async def _verify_login_on_threads(page) -> bool:
    """Verifikasi login di host threads.com lewat elemen navigasi, bukan sekadar nama cookie."""
    try:
        if "threads.com" not in (page.url or "").lower():
            await page.goto(VERIFY_URL, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(3.0)
        if "/login" in (page.url or "").lower():
            return False
        for selector in LOGGED_IN_SELECTORS:
            try:
                if await page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False
    except Exception as error:
        logger.debug(f"Verifikasi login threads.com gagal: {error}")
        return False



@ensure_proactor_loop
async def setup_threads_login(profile_dir: str = None) -> bool:
    """Buka browser GUI, polling login maks 10 menit, simpan sesi permanen.

    Kembalikan True bila login terverifikasi di threads.com, False bila timeout/gagal.
    """
    if profile_dir is None:
        profile_dir = str(THREADS_PROFILE_DIR)

    # Pastikan direktori profil ada
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("  THREADS / INSTAGRAM LOGIN SETUP")
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
            print("  SILAKAN LOGIN KE AKUN THREADS / INSTAGRAM ANDA PADA BROWSER YANG TERBUKA.")
            print("  Masukkan username, password, dan selesaikan 2FA/CAPTCHA jika ada.")
            print("  Script akan otomatis mendeteksi ketika login berhasil.")
            print("  Sesi akan tersimpan otomatis setelah login berhasil.")
            print("=" * 65 + "\n")

            max_checks  = MAX_WAIT_SEC // POLL_INTERVAL
            logged_in   = False

            for check in range(1, max_checks + 1):
                await asyncio.sleep(POLL_INTERVAL)

                if page.is_closed():
                    logger.info("Tab browser ditutup oleh pengguna.")
                    try:
                        cookies   = await context.cookies()
                        has_auth  = any(
                            c.get("name") in AUTH_COOKIES and bool(c.get("value"))
                            for c in cookies
                        )
                        hosts = sorted({
                            (c.get("domain") or "").lower()
                            for c in cookies
                            if c.get("name") == "sessionid" and c.get("value")
                        })
                        if has_auth and _host_is_allowed(hosts):
                            logged_in = True
                        else:
                            logger.warning(
                                "Cookie auth ditemukan tetapi tidak berlaku untuk threads.com "
                                f"(host: {', '.join(hosts) or '<kosong>'}). Sesi tidak dianggap valid."
                            )
                    except Exception:
                        pass
                    break

                try:
                    cookies         = await context.cookies()
                    has_session     = any(c.get("name") == "sessionid"  and bool(c.get("value")) for c in cookies)
                    has_ds_user     = any(c.get("name") == "ds_user_id" and bool(c.get("value")) for c in cookies)
                    current_url     = page.url.lower()

                    session_hosts = sorted({
                        (c.get("domain") or "").lower()
                        for c in cookies
                        if c.get("name") == "sessionid" and c.get("value")
                    })
                    host_ok = _host_is_allowed(session_hosts)

                    if has_session and has_ds_user and host_ok and "login" not in current_url:
                        # Verifikasi akhir di host threads.com: cookie saja tidak cukup,
                        # harus terbukti login pada host yang dipakai scraper.
                        if await _verify_login_on_threads(page):
                            logged_in = True
                            logger.info(
                                f"✓ Login terverifikasi di threads.com (cookie sessionid host: "
                                f"{', '.join(session_hosts)}) — login berhasil!"
                            )
                            break
                        logger.info(
                            "Cookie terdeteksi, tetapi threads.com belum menampilkan status login. "
                            "Menunggu..."
                        )
                    elif has_session and has_ds_user and not host_ok:
                        logger.info(
                            f"Menunggu cookie berlaku untuk threads.com... "
                            f"(host sessionid saat ini: {', '.join(session_hosts) or '<kosong>'})"
                        )

                    if "login" not in current_url:
                        for selector in LOGGED_IN_SELECTORS:
                            try:
                                if await page.locator(selector).count() > 0:
                                    # Pastikan minimal 1 cookie auth juga ada
                                    if has_session or has_ds_user:
                                        logged_in = True
                                        logger.info(f"✓ Elemen navigasi terdeteksi ({selector}) — login berhasil!")
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
                print(f"  SUKSES: LOGIN THREADS BERHASIL!")
                print(f"  Sesi tersimpan di: {profile_dir}")
                print("  Anda sekarang dapat menjalankan scraper Threads.")
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
    # python src/auth/login_threads.py [custom_profile_dir]
    profile = sys.argv[1] if len(sys.argv) > 1 else str(THREADS_PROFILE_DIR)
    result  = asyncio.run(setup_threads_login(profile))
    sys.exit(0 if result else 1)
