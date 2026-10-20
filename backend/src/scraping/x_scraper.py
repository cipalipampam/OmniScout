import asyncio
import json
import logging
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from parsel import Selector
from playwright.async_api import async_playwright, Page

# Pastikan BACKEND_DIR ada di sys.path
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from configs.config import X_PROFILE_DIR, EXPORTS_DIR, SCRAPER_CONFIG
from src.utils.async_compat import ensure_proactor_loop
from src.scraping.base_scraper import (
    create_browser, random_delay,
    results_to_dataframe, save_dataframe, append_checkpoint, check_profile_exists,
    keyword_matches_text, is_system_text as _system_text_matches,
)

logger = logging.getLogger("x_scraper")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")



DEFAULT_CHECKPOINT = str(EXPORTS_DIR / "x_checkpoint.csv")
DEFAULT_OUTPUT     = str(EXPORTS_DIR / "x_scraper_result.csv")



SYSTEM_EXACT_PHRASES = {
    "log in", "sign up", "masuk", "daftar",
    "what's happening", "apa yang sedang terjadi",
    "trending", "sedang tren", "trends for you", "tren untuk anda",
    "who to follow", "siapa yang harus diikuti",
    "show more", "tampilkan lebih banyak",
    "terms of service", "ketentuan layanan",
    "privacy policy", "kebijakan privasi",
    "cookie policy", "kebijakan cookie",
    "accessibility", "aksesibilitas",
    "ads info", "info iklan",
    "more", "lainnya", "explore", "jelajahi", "home", "beranda",
    "search", "cari", "notifications", "notifikasi", "messages", "pesan",
    "grok", "communities", "komunitas", "premium",
    "verified organizations", "organisasi terverifikasi",
    "profile", "profil", "settings", "pengaturan", "x", "x corp",
}

NOISE_EXACT = {
    "Translate post", "Terjemahkan postingan",
    "Show more", "Tampilkan lebih banyak",
    "Verified", "Terverifikasi",
    "Replying to", "Membalas",
    "Quote", "Kutip",
    "Promoted", "Dipromosikan",
}


def is_system_text(content: str) -> bool:
    """Filter teks antarmuka sistem X memakai implementasi bersama di base_scraper."""
    return _system_text_matches(content, SYSTEM_EXACT_PHRASES)



@dataclass
class XScrapeConfig:
    profile_dir       : str   = field(default_factory=lambda: str(X_PROFILE_DIR))
    headless          : bool  = True
    search_mode       : str   = field(default_factory=lambda: SCRAPER_CONFIG.get("search_mode", "latest"))
    goto_timeout_ms   : int   = field(default_factory=lambda: SCRAPER_CONFIG["goto_timeout_ms"])
    delay_range       : tuple = field(default_factory=lambda: SCRAPER_CONFIG["delay_range"])
    search_scroll     : int   = field(default_factory=lambda: SCRAPER_CONFIG["search_scroll"])
    max_links         : int   = field(default_factory=lambda: SCRAPER_CONFIG["max_links"])
    scan_step_px      : int   = field(default_factory=lambda: SCRAPER_CONFIG["scan_step_px"])
    scan_delay_range  : tuple = field(default_factory=lambda: SCRAPER_CONFIG["scan_delay_range"])
    scan_parse_every  : int   = 2
    scan_max_steps    : int   = field(default_factory=lambda: SCRAPER_CONFIG["scan_max_steps"])
    per_post_timeout_s: float = 1800.0


# JavaScript Snippet — Ekstraksi Komentar / Tweet dari DOM

_SYSTEM_EXACT_JS = json.dumps(sorted(SYSTEM_EXACT_PHRASES))
_NOISE_JS        = json.dumps(sorted(NOISE_EXACT))

_JS_EXTRACT_COMMENTS = f"""
() => {{
    const SYSTEM_EXACT = new Set({_SYSTEM_EXACT_JS});
    const NOISE = new Set({_NOISE_JS});
    const TIME_RE = /^\\d+[smhdw]$/i;
    const DATE_RE = /^(\\d{{1,2}}[\\/\\.-]\\d{{1,2}}[\\/\\.-]\\d{{2,4}}|\\d{{4}}[\\/\\.-]\\d{{1,2}}[\\/\\.-]\\d{{1,2}}|\\d{{1,2}}\\s+[a-z]{{3,9}}(\\s+\\d{{2,4}})?|[a-z]{{3,9}}\\s+\\d{{1,2}}(\\s+\\d{{2,4}})?)$/i;
    const COUNT_RE = /^\\d+([.,]\\d+)?[KMB]?$/i;
    const ACTION_NOISE_RE = /^(reply|repost|like|share|bookmark|copy link|salin tautan|suka|balas|posting ulang|bagikan|penanda|analytics|views|view post engagements|lihat interaksi postingan)$/i;

    const allTweets = document.querySelectorAll('article[data-testid="tweet"]');
    const results = [];
    const seen = new Set();

    for (const el of allTweets) {{
        const timeEl = el.querySelector('time[datetime]');
        if (!timeEl) continue;
        const dateVal = timeEl.getAttribute('datetime') || '';
        if (!dateVal) continue;

        let username = '';
        const userNameDiv = el.querySelector('div[data-testid="User-Name"]');
        if (userNameDiv) {{
            const allLinks = userNameDiv.querySelectorAll('a[href]');
            for (const link of allLinks) {{
                const href = link.getAttribute('href') || '';
                if (href.match(/^\\/[a-zA-Z0-9_]{{1,15}}$/)) {{
                    username = href.slice(1);
                    break;
                }}
            }}
            if (!username) {{
                const spans = userNameDiv.querySelectorAll('span');
                for (const sp of spans) {{
                    const t = (sp.textContent || '').trim();
                    if (t.startsWith('@')) {{ username = t.slice(1); break; }}
                }}
            }}
        }}
        if (!username) continue;

        const tweetTextDiv = el.querySelector('div[data-testid="tweetText"]');
        let content = '';
        if (tweetTextDiv) {{
            const walker = document.createTreeWalker(tweetTextDiv, NodeFilter.SHOW_TEXT, null);
            const tokens = [];
            let node;
            while (node = walker.nextNode()) {{
                const t = node.textContent.trim();
                if (t && !NOISE.has(t) && !ACTION_NOISE_RE.test(t)) tokens.push(t);
            }}
            content = tokens.join(' ').trim();
        }}
        if (!content || SYSTEM_EXACT.has(content.toLowerCase())) continue;

        const key = username + '|' + content;
        if (seen.has(key)) continue;
        seen.add(key);

        let type = 'Reply/Comment';
        const url = window.location.href;
        const statusMatch = url.match(/\\/status\\/(\\d+)/);
        const statusId = statusMatch ? statusMatch[1] : '';
        if (statusId) {{
            const timeAnchor = timeEl.closest('a[href]');
            if (timeAnchor) {{
                const timeHref = timeAnchor.getAttribute('href') || '';
                if (timeHref.includes(statusId)) type = 'Original Post';
            }}
        }}

        results.push({{ user_id: username, date: dateVal, content: content, type: type }});
    }}
    return results;
}}
"""

_JS_EXTRACT_SEARCH_CARDS = """
() => {
    const articles = document.querySelectorAll('article[data-testid="tweet"]');
    const results = [];
    const seenUrls = new Set();
    for (const article of articles) {
        const statusLinks = article.querySelectorAll('a[href*="/status/"]');
        let url = '';
        for (const link of statusLinks) {
            const href = link.href || '';
            if (href.match(/\\/status\\/\\d+$/) || href.match(/\\/status\\/\\d+\\?/)) {
                url = href.split('?')[0].split('#')[0].replace(/\\/$/, '');
                break;
            }
        }
        if (!url || seenUrls.has(url)) continue;
        const tweetTextDiv = article.querySelector('div[data-testid="tweetText"]');
        let fullText = tweetTextDiv ? (tweetTextDiv.textContent || '').trim() : '';
        if (!fullText) {
            const tokens = [];
            for (const da of article.querySelectorAll('[dir="auto"]')) {
                const t = (da.textContent || '').trim();
                if (t) tokens.push(t);
            }
            fullText = tokens.join(' ');
        }
        seenUrls.add(url);
        results.push({ url: url, text: fullText });
    }
    return results;
}
"""



async def _check_thread_divider(page: Page, step: int = 0) -> bool:
    """Deteksi tanda pembatas akhir reply di postingan X (hanya di kolom utama)."""
    if step < 5:
        return False
    try:
        return await page.evaluate("""() => {
            const primary = document.querySelector('div[data-testid="primaryColumn"]') || document.querySelector('main[role="main"]');
            if (!primary) return false;
            const targets = ['discover more', 'temukan lebih banyak', 'more tweets', 'postingan lainnya', 'more replies', 'balasan lainnya'];
            const elements = primary.querySelectorAll('h2, h3, h4, [role="heading"], div[dir="auto"], span[dir="auto"]');
            for (const el of elements) {
                const txt = (el.textContent || '').trim().toLowerCase();
                if (txt.length > 0 && txt.length < 50) {
                    for (const t of targets) {
                        if (txt === t || txt.startsWith(t)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.top > 0 && rect.top < window.innerHeight + 300) return true;
                        }
                    }
                }
            }
            return false;
        }""")
    except Exception as e:
        logger.debug(f"_check_thread_divider error: {e}")
        return False


async def _click_expand_buttons(page: Page) -> int:
    """Klik tombol 'Show replies' / 'Show more replies' secara otomatis."""
    try:
        clicked = await page.evaluate("""() => {
            const primary = document.querySelector('div[data-testid="primaryColumn"]') || document.querySelector('main[role="main"]') || document;
            const patterns = [/show\\s+more\\s+repl/i, /show\\s+repl/i, /show\\s+\\d+\\s+repl/i,
                              /tampilkan\\s+balasan/i, /tampilkan\\s+lebih\\s+banyak\\s+balasan/i,
                              /tampilkan\\s+\\d+\\s+balasan/i, /more\\s+repl/i, /view\\s+repl/i,
                              /lihat\\s+balasan/i, /balasan\\s+lainnya/i, /probable\\s+spam/i, /mungkin\\s+spam/i];
            let count = 0;
            const candidates = primary.querySelectorAll('div[role="button"], span[role="button"], button, [tabindex="0"]');
            for (const el of candidates) {
                const text = (el.textContent || '').trim();
                if (!text || text.length > 80) continue;
                for (const pat of patterns) {
                    if (pat.test(text)) {
                        if (el.offsetWidth > 0 && el.offsetHeight > 0) {
                            const rect = el.getBoundingClientRect();
                            if (rect.top > -150 && rect.top < window.innerHeight + 350) {
                                el.click(); count++; break;
                            }
                        }
                    }
                }
            }
            return count;
        }""")
        return clicked or 0
    except Exception as e:
        logger.debug(f"_click_expand_buttons error: {e}")
        return 0


async def _collect_js_items(page: Page, source_link: str, collected: dict) -> int:
    """Eksekusi JS extractor dan masukkan hasilnya ke dict 'collected' tanpa duplikasi."""
    count_before = len(collected)
    try:
        items = await page.evaluate(_JS_EXTRACT_COMMENTS)
        for item in items:
            key = (item["user_id"], item["content"])
            if key not in collected:
                collected[key] = {
                    "platform"     : "X",
                    "source"       : source_link,
                    "user_id"      : item["user_id"],
                    "type"         : item["type"],
                    "date"         : item["date"],
                    "content"      : item["content"],
                }
    except Exception as e:
        logger.debug(f"JS extraction error: {e}")
    return len(collected) - count_before



async def _slow_scan_comments(page: Page, source_link: str, config: XScrapeConfig) -> list[dict]:
    """Ekstrak tweet + seluruh reply via micro-step forward scan + reverse sweep."""
    CONFIRM_ROUNDS  = 5
    LOG_EVERY       = 20
    EXPAND_EVERY    = 2
    REVERSE_STEP_PX = 250

    collected: dict[tuple, dict] = {}
    confirm_streak = 0
    step = 0
    last_log_count = 0

    for step in range(config.scan_max_steps):
        try:
            has_divider = await _check_thread_divider(page, step=step)
            if has_divider:
                await _collect_js_items(page, source_link, collected)
                logger.info(f"Thread divider terdeteksi pada step {step + 1}. Berhenti forward scan.")
                break

            got_new = False
            if step % config.scan_parse_every == 0:
                new_added = await _collect_js_items(page, source_link, collected)
                got_new = new_added > 0
                if len(collected) - last_log_count >= LOG_EVERY:
                    logger.info(f"Progress: {len(collected)} komentar (step {step + 1})...")
                    last_log_count = len(collected)

            if step > 0 and step % EXPAND_EVERY == 0:
                expanded = await _click_expand_buttons(page)
                if expanded > 0:
                    logger.info(f"Auto-expand {expanded} reply thread(s)...")
                    await asyncio.sleep(1.5)

            metrics_before = await page.evaluate("() => ({ height: document.body.scrollHeight, scrollY: window.scrollY })")
            await page.evaluate(f"window.scrollBy({{ top: {config.scan_step_px}, behavior: 'auto' }})")
            await random_delay(config.scan_delay_range)
            metrics_after = await page.evaluate("() => ({ height: document.body.scrollHeight, scrollY: window.scrollY })")

            height_grew    = metrics_after["height"] > metrics_before["height"]
            scrolled_moved = abs(metrics_after["scrollY"] - metrics_before["scrollY"]) > 10

            if got_new or height_grew or scrolled_moved:
                confirm_streak = 0
                continue

            confirm_streak += 1
            logger.info(f"Konfirmasi stagnasi {confirm_streak}/{CONFIRM_ROUNDS} ({len(collected)} item)...")
            if confirm_streak >= CONFIRM_ROUNDS:
                break

            await _click_expand_buttons(page)
            await asyncio.sleep(1.0)
            nudge_added = await _collect_js_items(page, source_link, collected)
            if nudge_added > 0:
                confirm_streak = 0

        except Exception as e:
            logger.warning(f"Forward scan berhenti pada step {step}: {e}")
            break

    forward_count = len(collected)
    logger.info(f"Forward scan selesai: {forward_count} item dari {step + 1} langkah.")

    try:
        scroll_height  = await page.evaluate("document.body.scrollHeight")
        current_pos    = scroll_height
        max_reverse    = int(scroll_height / REVERSE_STEP_PX) + 100
        reverse_steps  = 0
        while current_pos > 0 and reverse_steps < max_reverse:
            await page.evaluate(f"window.scrollBy(0, -{REVERSE_STEP_PX})")
            await asyncio.sleep(0.25)
            await _collect_js_items(page, source_link, collected)
            current_pos -= REVERSE_STEP_PX
            reverse_steps += 1
    except Exception as e:
        logger.warning(f"Reverse sweep berhenti: {e}")

    reverse_gained = len(collected) - forward_count
    if reverse_gained > 0:
        logger.info(f"Reverse sweep menambah {reverse_gained} item baru!")

    try:
        final_expanded = await _click_expand_buttons(page)
        if final_expanded > 0:
            await asyncio.sleep(3.0)
        await random_delay((1.0, 1.8))
        await _collect_js_items(page, source_link, collected)
    except Exception as e:
        logger.debug(f"Final settle dilewati: {e}")

    try:
        html = await page.content()
        for item in _parse_post_page_html(html, source_link):
            key = (item["user_id"], item["content"])
            if key not in collected:
                collected[key] = item
    except Exception as e:
        logger.warning(f"HTML consolidation gagal: {e}")

    logger.info(f"Total komentar unik: {len(collected)}")
    return list(collected.values())



_ACTION_NOISE_RE = re.compile(r'^(reply|repost|like|share|bookmark|copy link|salin tautan|suka|balas|posting ulang|bagikan|penanda|analytics|views)$', re.IGNORECASE)


def _extract_post_id(post_url: str) -> str:
    match = re.search(r"/status/(\d+)", post_url)
    return match.group(1) if match else ""


def _parse_post_page_html(html: str, source_link: str) -> list[dict]:
    """Fallback parser berbasis Parsel untuk mengekstrak tweet dari HTML statik."""
    sel = Selector(text=html)
    target_post_id = _extract_post_id(source_link)

    articles = sel.xpath('//article[@data-testid="tweet"]')
    if not articles:
        articles = sel.xpath('//article[.//time[@datetime]]')

    results = []
    seen = set()
    for article in articles:
        all_hrefs = article.xpath('.//a/@href').getall()
        username = ""
        for h in all_hrefs:
            h_clean = h.strip().rstrip("/")
            if re.match(r'^/[a-zA-Z0-9_]{1,15}$', h_clean):
                username = h_clean[1:]
                break
        if not username:
            continue

        date_val = article.xpath(".//time/@datetime").get()
        if not date_val:
            continue

        # Coba ekstrak dari tweetText dulu
        noise = NOISE_EXACT | {username}
        tweet_text_nodes = article.xpath('.//*[@data-testid="tweetText"]//text()').getall()
        if tweet_text_nodes:
            clean_tokens = [t.strip() for t in tweet_text_nodes
                            if t.strip() and t.strip() not in noise and not _ACTION_NOISE_RE.match(t.strip())]
            content = " ".join(clean_tokens).strip()
        else:
            content = ""

        if not content or is_system_text(content):
            continue

        dedup_key = (username, content)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Klasifikasi Original Post / Reply
        post_type = "Reply/Comment"
        if target_post_id:
            time_href = article.xpath('.//time[@datetime]/ancestor::a[1]/@href').get()
            if time_href and target_post_id in time_href:
                post_type = "Original Post"

        results.append({
            "platform"      : "X",
            "source"        : source_link,
            "user_id"       : username,
            "type"          : post_type,
            "date"          : date_val,
            "content"       : content,
        })
    return results



# Keyword matching dipindah ke base_scraper.keyword_matches_text() (satu
# implementasi bersama dengan Threads) — lihat blok import di atas.



async def collect_post_urls(
    page: Page,
    keyword: str,
    config: XScrapeConfig,
    status_callback: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Stage 1: kumpulkan URL tweet relevan dari halaman pencarian X."""
    # Kuota discovery & uji relevansi berlaku per keyword yang sedang diproses.
    match_keywords = [keyword]
    encoded_query  = urllib.parse.quote(keyword)

    if config.search_mode.lower() == "top":
        search_url = f"https://x.com/search?q={encoded_query}&src=typed_query"
        mode_label = "TOP / Terpopuler"
    else:
        search_url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"
        mode_label = "LATEST / Terbaru"

    logger.info(f"--- Stage 1: Mencari URL ({mode_label}) untuk keyword '{keyword}' ---")
    if status_callback:
        status_callback(f"[X] Mencari URL tweet ({mode_label}) untuk keyword '{keyword}'...")

    seen_urls: set[str] = set()
    ordered_urls: list[str] = []
    skipped_count = 0

    SCROLL_STEP_PX  = 850
    STALE_LIMIT     = 20  # Toleransi stagnasi lebih tinggi (20 round) agar timeline sempat memuat

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=config.goto_timeout_ms)
        await random_delay((3.0, 5.0))

        stale_count = 0
        for scroll_round in range(1, config.search_scroll + 1):
            await page.evaluate(f"window.scrollBy({{ top: {SCROLL_STEP_PX}, behavior: 'smooth' }})")
            await random_delay(config.delay_range)

            cards = await page.evaluate(_JS_EXTRACT_SEARCH_CARDS)
            new_kept = 0
            new_skipped = 0
            for card in cards:
                url = card["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                if keyword_matches_text(card["text"], match_keywords):
                    ordered_urls.append(url)
                    new_kept += 1
                else:
                    new_skipped += 1
                    skipped_count += 1

            if new_kept > 0:
                stale_count = 0
                msg = f"  Scroll #{scroll_round}: +{new_kept} URL relevan (total: {len(ordered_urls)}, dilewati: {skipped_count})"
                logger.info(msg)
                if status_callback:
                    status_callback(f"[X] Mengumpulkan URL ({len(ordered_urls)}/{config.max_links} tweet relevan ditemukan)...")
            elif new_skipped > 0:
                stale_count = 0
            else:
                stale_count += 1

            if len(ordered_urls) >= config.max_links:
                logger.info(f"  Kuota {config.max_links} URL tercapai pada scroll #{scroll_round}.")
                if status_callback:
                    status_callback(f"[X] Kuota {config.max_links} URL berhasil tercapai.")
                break

            if stale_count >= STALE_LIMIT:
                logger.info(f"  Tidak ada tweet baru selama {STALE_LIMIT} scroll berturut-turut. Mengakhiri Stage 1.")
                break

        ordered_urls = ordered_urls[:config.max_links]
        summary_msg = f"Stage 1 selesai: {len(ordered_urls)} URL relevan dari {len(seen_urls)} total tweet terdeteksi."
        logger.info(summary_msg)
        if status_callback:
            status_callback(f"[X] {summary_msg}")

    except Exception as e:
        logger.warning(f"Stage 1 gagal untuk keyword '{keyword}': {e}")

    return ordered_urls



async def deep_crawl_post(
    page: Page,
    link: str,
    config: XScrapeConfig,
    max_retries: int = 2,
    status_callback: Optional[Callable[[str], None]] = None,
) -> list[dict]:
    """Stage 2: crawl satu URL tweet + seluruh reply; kembalikan list dict (kosong bila gagal)."""
    logger.info(f"Deep Crawling : {link}")
    for attempt in range(1, max_retries + 2):
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=config.goto_timeout_ms)
            await random_delay(config.delay_range)
            results = await asyncio.wait_for(
                _slow_scan_comments(page, link, config),
                timeout=config.per_post_timeout_s,
            )
            return results
        except asyncio.TimeoutError:
            logger.warning(f"Timeout pada {link}. Lanjut ke postingan berikutnya.")
            return []
        except Exception as e:
            if attempt <= max_retries:
                wait_s = 2 ** attempt
                logger.warning(f"Error pada {link} (attempt {attempt}/{max_retries + 1}): {e}. Retry dalam {wait_s}s...")
                await asyncio.sleep(wait_s)
            else:
                logger.warning(f"Gagal setelah {max_retries + 1} attempt pada {link}. Di-skip.")
                return []



@ensure_proactor_loop
async def run_x_scraper(
    keywords       : list[str] = None,
    direct_urls    : list[str] = None,
    config         : XScrapeConfig = None,
    checkpoint_path: str = DEFAULT_CHECKPOINT,
    final_path     : str = DEFAULT_OUTPUT,
    status_callback: Optional[Callable[[str], None]] = None,
) -> "pd.DataFrame":
    """Pipeline lengkap X (Twitter): Stage 1 cari URL → Stage 2 deep crawl → DataFrame."""
    config      = config or XScrapeConfig()
    keywords    = keywords or []
    direct_urls = direct_urls or []

    if not check_profile_exists(config.profile_dir):
        logger.error(
            f"Sesi X belum ditemukan di '{config.profile_dir}'. "
            "Jalankan 'python -m src.auth.login_x' terlebih dahulu."
        )
        return pd.DataFrame()

    all_results    : list[dict] = []
    global_seen_urls: set[str] = set()

    async with async_playwright() as p:
        try:
            context, page = await create_browser(p, config.profile_dir, config.headless)
        except RuntimeError as e:
            logger.error(str(e))
            return pd.DataFrame()

        try:
            cookies     = await context.cookies()
            has_auth    = any(c.get("name") == "auth_token" and bool(c.get("value")) for c in cookies)
            has_twid    = any(c.get("name") == "twid"       and bool(c.get("value")) for c in cookies)

            if not (has_auth or has_twid):
                logger.warning("Cookie auth_token/twid tidak ditemukan. Periksa status login X.")

            try:
                await page.goto("https://x.com/home", timeout=60_000)
            except Exception:
                pass

            session_urls: list[str] = []

            for u in direct_urls:
                if u not in global_seen_urls:
                    global_seen_urls.add(u)
                    session_urls.append(u)

            for kw in keywords:
                urls = await collect_post_urls(
                    page,
                    kw,
                    config,
                    status_callback=status_callback,
                )
                for u in urls:
                    if u not in global_seen_urls:
                        global_seen_urls.add(u)
                        session_urls.append(u)

            logger.info(f"Total URL untuk di-crawl: {len(session_urls)}")

            if not session_urls:
                msg_empty = "Tidak ada URL yang ditemukan. Coba periksa keyword atau sesi login."
                logger.warning(msg_empty)
                if status_callback:
                    status_callback(f"[X] {msg_empty}")
                return pd.DataFrame()

            total_urls = len(session_urls)
            for idx, link in enumerate(session_urls, start=1):
                logger.info(f"[{idx}/{total_urls}] {link}")
                if status_callback:
                    status_callback(f"[X] Tahap 2: Deep Crawl postingan {idx}/{total_urls} ({link})...")

                post_data = await deep_crawl_post(page, link, config, status_callback=status_callback)
                if post_data:
                    all_results.extend(post_data)
                    append_checkpoint(post_data, checkpoint_path)
                await random_delay(config.delay_range)

        finally:
            try:
                await context.close()
            except Exception:
                pass

    df = results_to_dataframe(all_results)
    if not df.empty:
        save_dataframe(df, final_path)
        logger.info(f"Scraping X selesai. Total: {len(df)} baris. File: {final_path}")
    else:
        logger.warning("Tidak ada data yang terkumpul dari sesi ini.")
    return df



if __name__ == "__main__":
    keywords = sys.argv[1:] if len(sys.argv) > 1 else []
    if not keywords:
        print("Penggunaan: python x_scraper.py <keyword1> [keyword2 ...]")
        sys.exit(1)
    df_result = asyncio.run(run_x_scraper(keywords=keywords))
    print(f"\nHasil: {len(df_result)} baris terkumpul.")
