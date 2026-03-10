from pathlib import Path
import os
import sys
import time
import threading
import re
import shutil
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(
        os.path.dirname(sys.executable), "_internal", "ms-playwright"
    )
else:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = ""

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
# ===== CONFIG =====
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")
HISTORY_DIR = os.path.join(BASE_DIR, "history")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
GUARD_PATH = os.path.join(BASE_DIR, ".runtime_guard")
SESSION_LOCK = os.path.join(BASE_DIR, ".session_lock")
LOGIN_TRUST_PATH = os.path.join(BASE_DIR, ".login_trust.txt")
login_trust = (os.path.exists(LOGIN_TRUST_PATH))
LINKS_FILE = os.path.join(HISTORY_DIR, "links.txt")
warned_unverified = False


os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.pinterest.com/"
}

SCROLL_STEP = 500
MAX_WAIT_AFTER_SCROLL = 3.0
POLL_INTERVAL = 0.2



# ===== COLORS & STYLES =====
class Color:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright versions
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    

    
# ===== SPINNER =====
class Spinner:
    def __init__(self, interval=0.1):
        self.frames = "◐◓◑◒"
        self.interval = interval
        self.running = False
        self.thread = None

    def _spin(self):
        i = 0
        while self.running:
            frame = self.frames[i % len(self.frames)]
            sys.stdout.write(f"\r{frame} Extracting ")
            sys.stdout.flush()
            time.sleep(self.interval)
            i += 1

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        sys.stdout.write("\r  \r")
        sys.stdout.flush()
    
if os.name == "nt":
    os.system("")
   
# HELPERS
TOTAL_STEPS = 4
_login_step  = 0



def normalize_link(link: str) -> str:
    link = link.strip()
    parsed = urlparse(link)

    scheme = "https"
    netloc = parsed.netloc.lower()

    # remove trailing slash
    path = parsed.path.rstrip("/")

    return f"{scheme}://{netloc}{path}"

def load_links() -> set:
    if not LINKS_FILE.exists():
        return set()

    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}
    
def show_existing_links() -> set:
    links = load_links()
    
    print(styled_text("─" * 50, Color.DIM))
    print("\033[1mExisting links:\033[0m")
    for l in links:
        print(l)
    print(styled_text("─" * 50, Color.DIM))

    return links

def append_link(link: str):
    with open(LINKS_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")

def check_and_append(url: str, links: set) -> bool:
    normalized = normalize_link(url)

    if normalized in links:
        return False
    else:
        append_link(normalized)
        links.add(normalized)   # keep memory consistent
        return True




def remove_login_trust():
    for p in (LOGIN_TRUST_PATH, LOGIN_TRUST_PATH + ".txt"):
        if os.path.exists(p):
            os.remove(p)

def login_progress(label):
    global _login_step
    _login_step += 1
    bar = progress_bar(_login_step, TOTAL_STEPS)
    print(f"\r\033[K  {bar}  {styled_text(label, Color.DIM)}", end="", flush=True)

def login_progress_done():
    print()

def guard_write(state: str):
    with open(GUARD_PATH, "w", encoding="utf-8") as f:
        f.write(state)

def guard_read():
    if not os.path.exists(GUARD_PATH):
        return None
    try:
        with open(GUARD_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return None

def guard_clear():
    if os.path.exists(GUARD_PATH):
        os.remove(GUARD_PATH)
        
def handle_keyboard_interrupt(last_state):
    if last_state in (None, "INIT"):
        guard_clear()
    release_session_lock()
    print()
    print_info("Interrupted by user.")
    safe_exit(130)
    
def acquire_session_lock():
    try:
        fd = os.open(SESSION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
    except FileExistsError:
        print_warning("Another PinRecon session may already be running.")
        print_info("r → remove previous session | c → continue anyway | e → exit")
        choice = ask_choice("Choice (r/c/e): ", {"r","c","e"})
        
        if choice == "e":
            sys.exit(0)

        if choice == "r":
            os.remove(SESSION_LOCK)
            print_success("Previous session lock cleared.")


def release_session_lock():
    if os.path.exists(SESSION_LOCK):
        os.remove(SESSION_LOCK)
        
def safe_exit(code=0, message=None):
    if message:
        print_info(message)

    guard_clear()
    release_session_lock()
    input("\nPress Enter to exit...")
    sys.exit(code)
    
def verify_logged_in(USER_DATA_DIR):
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            ctx = p.firefox.launch_persistent_context(
                USER_DATA_DIR,
                headless=True
            )
            page = ctx.new_page()
            page.goto("https://www.pinterest.com/me/", wait_until="domcontentloaded", timeout=20000)
            final_url = page.url
            ctx.close()

        return "/login" not in final_url
    except Exception:
        # Any timeout, network error, block, or crash = NOT logged in
        return False
    
def ask_choice(prompt, valid):
    while True:
        c = input(styled_text(f"❯ {prompt}", Color.BRIGHT_CYAN)).strip().lower()
        if c in valid:
            return c
        print_error(f"Invalid input. Choose from: {', '.join(valid)}")

def ask_board_url():
    while True:
        url = input(styled_text("❯ Paste the Pinterest board URL: ", Color.BRIGHT_CYAN)).strip()
        
        if not url:
            print_error("Board URL cannot be empty.")
            continue
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            print_error("URL must start with http:// or https://")
            continue
        
        # Validate it's a board URL (has username and board name)
        # Format: https://[region.]pinterest.com/username/board-name/
        url_pattern = r'pinterest\.com/[^/]+/[^/]+'
        if not re.search(url_pattern, url):
            print_error("Invalid board URL format. Expected: https://pinterest.com/username/board-name/")
            print(styled_text("  Example: https://in.pinterest.com/username/board-name/", Color.DIM))
            continue
            
        return url

def resolve_originals(img):
    if not img:
        return None
    srcset = img.get_attribute("srcset")
    src = img.get_attribute("src")
    cur = img.get_attribute("currentSrc")
    candidates = []
    if srcset:
        candidates.append(srcset.split(",")[-1].split(" ")[0])
    candidates += [cur, src]
    for u in candidates:
        if not u:
            continue
        if "/originals/" in u:
            return u
        for s in ("236x", "474x", "564x", "736x"):
            if f"/{s}/" in u:
                return u.replace(f"/{s}/", "/1200x/")
    return None

# BOARD ID DETECTION
def detect_board_id(page):
    board_id = None

    def handle(route, request):
        nonlocal board_id

        if "BoardFeedResource/get" not in request.url:
            return route.continue_()

        try:
            resp = route.fetch()
            data = resp.json()

            pins = data.get("resource_response", {}).get("data", [])
            if pins and not board_id:
                board_id = pins[0].get("board", {}).get("id")

            route.fulfill(response=resp)
        except Exception:
            route.continue_()

    page.route("**/BoardFeedResource/get**", handle)

    def getter():
        return board_id

    return getter

def styled_text(text, *styles):
    """Apply multiple styles to text"""
    return ''.join(styles) + text + Color.RESET

def print_header():
    print()
    print(styled_text("=" * 60, Color.WHITE, Color.BOLD))
    print()
    print(styled_text("  📌 PinRecon: Pinterest Board Pin Extractor & Downloader", Color.GREEN, Color.BOLD))
    print(styled_text("     Version 1.5.1", Color.WHITE))
    print()
    print(styled_text("=" * 60, Color.WHITE, Color.BOLD))
    print()

def print_section(title, icon="►"):
    """Print a section header"""
    print(styled_text(f"\n{icon} {title}", Color.BRIGHT_YELLOW, Color.BOLD))
    print(styled_text("─" * 50, Color.DIM))

def print_success(text):
    """Print success message"""
    print(styled_text("✓ ", Color.BRIGHT_GREEN, Color.BOLD) + text)

def print_info(text):
    """Print info message"""
    print(styled_text("ℹ  ", Color.BRIGHT_BLUE, Color.BOLD) + text)

def print_warning(text):
    """Print warning message"""
    print(styled_text("⚠  ", Color.BRIGHT_YELLOW, Color.BOLD) + text)

def print_error(text):
    """Print error message"""
    print(styled_text("✗ ", Color.BRIGHT_RED, Color.BOLD) + text)

def progress_bar(current, total, width=40):
    """Generate a progress bar"""
    if total == 0:
        percent = 100
    else:
        percent = (current / total) * 100
    
    filled = int(width * current // total) if total > 0 else width
    bar = "█" * filled + "░" * (width - filled)
    
    return f"{styled_text(bar, Color.BRIGHT_CYAN)} {styled_text(f'{percent:.1f}%', Color.BRIGHT_WHITE)} ({current}/{total})"

# Clear screen
os.system('cls' if os.name == 'nt' else 'clear')

# ================= MAIN =================
def main():
    global login_trust, warned_unverified

    print_info("Press Ctrl+C at any time to exit safely.")

    acquire_session_lock()
    
    last_state = guard_read()
    
    
    try:
        if last_state in {"LOGIN_VERIFIED", "BOARD_SELECTED", "EXTRACTION_COMPLETE"}:
            print_warning("Previous run did not exit cleanly. Recovering...")
            
            if last_state == "LOGIN_VERIFIED":
                print_info("Login was verified previously. Resuming from board selection.")

            elif last_state == "BOARD_SELECTED":
                print_info("Board was selected previously.")
                print_info("Recovery is informational only. Re-selecting board.")

            elif last_state == "EXTRACTION_COMPLETE":
                print_info("Pins were extracted previously. Resuming download decision.")
                
            guard_write("INIT")
        
        print_header()
        # LOGIN
        print_section("Login Status", "🔐")
        if os.path.exists(USER_DATA_DIR):
            print_success("Login profile detected")
            print_info("c → continue | r → reset login | e → exit")
            choice = ask_choice("Choice (c/r/e): ", {"c","r","e"})
            
            if choice == "e":
                safe_exit(0)
                
            elif choice == "r":
                print_warning("This will delete your login data. Do you want to continue?")
                really = ask_choice("Choice (y/n): ", {"y","n"})
                if really == "y":
                    shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
                    remove_login_trust()
                    login_trust = False
                    print_success("Login reset.\n")    
                    safe_exit(0, "Restart the program to continue.")

                elif really == "n":
                    safe_exit(0)

                
            elif choice == "c":
                if not login_trust and not warned_unverified:
                    print_warning(
                        "Login state is unverified and probably corrupted.\n"
                        "Public boards may extract with missing pins.\n"
                        "Private boards require valid login.\n" 
                        "Advice: (ctrl+c → Restart → reset login) \n"
                        "or continue."
                    )
                    warned_unverified = True

                links = show_existing_links()  
                BOARD_URL = ask_board_url()
                check_and_append(BOARD_URL, links)
            
            
        else:
            print_info("No login profile found")
            print(f"  {styled_text('c', Color.BRIGHT_GREEN)} → Create login")
            print(f"  {styled_text('e', Color.BRIGHT_RED)} → Exit")
            
            if ask_choice("Choice (c/e): ", {"c", "e"}) == "e":
                safe_exit(0, "Exiting...")
                
            print_section("Browser Login", "🌐")
            
            print(styled_text("  → Log in to Pinterest", Color.DIM))
            print(styled_text("  → Close the browser when done", Color.DIM))
            
            login_progress("Launching browser for Pinterest login")
                        
            with sync_playwright() as p:
                ctx = p.firefox.launch_persistent_context(USER_DATA_DIR, headless=False)
                page = ctx.new_page()
                page.goto("https://www.pinterest.com/login/")
                login_progress("Waiting for user login")
                page.wait_for_event("close", timeout=0)
                ctx.close()
            
            login_progress("Verifying login with Pinterest servers")    
            
            if not verify_logged_in(USER_DATA_DIR):
                print_error("Login failed. Cleaning up...")
                print_warning("Deleting invalid login profile.")
                shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
                remove_login_trust()
                login_trust = False
                print_warning("Restart the program to continue.")
                safe_exit(1)
                
                 
                
            login_progress("Login confirmed")
            login_progress_done()
            print()
            print_success("Login confirmed.")
            
            login_trust = True
            with open(LOGIN_TRUST_PATH, "w") as f:
                f.write("verified")
                
            guard_write("LOGIN_VERIFIED")

            links = show_existing_links()  
            BOARD_URL = ask_board_url()
            guard_write("BOARD_SELECTED")
            check_and_append(BOARD_URL, links)

        # EXTRACTION
        print_section("Board Extraction", "🎯")
        print_info("Initializing browser...")
        start = time.time()

        with sync_playwright() as p:
            context = p.firefox.launch_persistent_context(USER_DATA_DIR, headless=True)
            page = context.new_page()
            board_id_getter = detect_board_id(page)
            
            print_info("Loading board...")
            
            try:
                page.goto(BOARD_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
            except Exception as e:
                print_error(f"Failed to load board: {str(e)}")
                print_warning("Please check:")
                print(styled_text("  • Your internet connection", Color.DIM))
                print(styled_text("  • The board URL is correct", Color.DIM))
                print(styled_text("  • The board is not deleted", Color.DIM))
                print(styled_text("  • If nothing works, Clear login data and login again.", Color.DIM))
                context.close()
                safe_exit(1)
                
            board_id = board_id_getter()
            if not board_id:
                print_error(
                    "Failed to detect board ID.\n"
                    "This usually indicates a private board with invalid login.\n\n"
                    "Action:\n"
                    "Clear login data and log in again."
                    )
                safe_exit(1)

            board_name = BOARD_URL.rstrip("/").split("/")[-1]
            formatted_name = re.sub(r'[_\-\.]+', ' ', board_name).title()
            print(f"  {styled_text('Board ID:', Color.BRIGHT_WHITE)}   {styled_text(board_id, Color.BRIGHT_CYAN)}")
            print(f"  {styled_text('Board Name:', Color.BRIGHT_WHITE)} {styled_text(formatted_name, Color.BRIGHT_MAGENTA)}")


            HISTORY_PATH = os.path.join(HISTORY_DIR, f"{board_id}.txt")
            
            # ----- LOAD HISTORY
            history_map = {}  # pin_id -> img_url
            if os.path.exists(HISTORY_PATH):
                with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        if "|" not in line:
                            print_warning(f"Skipping corrupted history line {line_num}")
                            continue
                        try:
                            pid, img_url = line.split("|", 1)
                            history_map[pid] = img_url
                        except Exception:
                            print_warning(f"Skipping malformed history line {line_num}")
                            continue
            history_ids = set(history_map.keys())
            
            try:
                page.wait_for_selector('[data-test-id="pin-count"]', timeout=20000)
                TOTAL_PINS = int(page.locator('[data-test-id="pin-count"]').inner_text().split()[0])
            except:
                TOTAL_PINS = 200000

            delta_new_pins = max(TOTAL_PINS - len(history_ids), 0)
            print(f"  {styled_text('Total Pins:', Color.BRIGHT_WHITE)}  {styled_text(str(TOTAL_PINS), Color.BRIGHT_GREEN)}")
            
            if len(history_ids) > 0:
                print(f"  {styled_text('In History:', Color.BRIGHT_WHITE)}  {styled_text(str(len(history_ids)), Color.BRIGHT_YELLOW)}")
                print(f"  {styled_text('New Pins:', Color.BRIGHT_WHITE)}    {styled_text(str(delta_new_pins), Color.BRIGHT_GREEN)}")


            print()
            
            
            seen, pins, idle = set(), [], 0
            board_prefix, last_dom_ids = None, set()
            last_print = time.time()
            spinner = Spinner()
            spinner.start()
            while True:
                current_dom_ids = set(
                    pid for pid in page.eval_on_selector_all(
                        'div[data-test-id="pin"][data-test-pin-id]',
                        "els => els.map(e => e.getAttribute('data-test-pin-id'))"
                    ) if pid
                )

                snapshot_new = 0

                for pid in current_dom_ids:  #- for pid in new_dom_ids:  + for pid in current_dom_ids:
                    if pid in seen:
                        continue
                    seen.add(pid)

                    if board_prefix is None:
                        board_prefix = pid[:9]
                    if not pid.startswith(board_prefix):
                        continue
                    
                    if pid not in history_ids:

                        pin_el = page.query_selector(f'div[data-test-pin-id="{pid}"]')
                        if not pin_el:
                            continue

                        img = pin_el.query_selector("img")
                        pins.append({
                            "id": pid,
                            "url": f"https://www.pinterest.com/pin/{pid}/",
                            "img_url": resolve_originals(img)
                        })
                        snapshot_new += 1
                        print(f"\r {snapshot_new} new pins...", end="", flush=True)
                    
                    # Progress bar (update every 5% or every second)
                    current_time = time.time()
                    if len(pins) >= TOTAL_PINS or current_time - last_print >= 1:
                        print(f"\r  {progress_bar(len(pins), TOTAL_PINS)}", end="", flush=True)
                        last_print = current_time
                    
                    
                    if len(pins) >= TOTAL_PINS:
                        break

                if len(pins) >= TOTAL_PINS:
                    print(f"\r  {progress_bar(len(pins), TOTAL_PINS)}")
                    break

                idle = 0 if snapshot_new else idle + 1
                if idle > 10:
                    print(f"\r  {progress_bar(len(pins), TOTAL_PINS)}")
                    break

                dom_before = set(current_dom_ids)
                page.evaluate(f"window.scrollBy(0, {SCROLL_STEP})")

                start_wait = time.time()
                while time.time() - start_wait < MAX_WAIT_AFTER_SCROLL:
                    dom_after = set(
                        pid for pid in page.eval_on_selector_all(
                            'div[data-test-id="pin"][data-test-pin-id]',
                            "els => els.map(e => e.getAttribute('data-test-pin-id'))"
                        ) if pid
                    )
                    if dom_after - dom_before:
                        break
                    time.sleep(POLL_INTERVAL)
            spinner.stop()  
            context.close()

        # SAVE HISTORY
        with open(HISTORY_PATH, "a", encoding="utf-8") as f:
            new_pins = []
            for p in pins:
                pid = p["id"]
                url = p["url"]
                img_url = p["img_url"]
                
                if not img_url:
                    continue
                
                if pid not in history_map:
                    f.write(f"{pid}|{img_url}\n")
                    history_map[pid] = img_url
                    
                    new_pins.append({
                        "id": pid,
                        "url": url,
                        "img_url": img_url
                    })
                    
        extraction_time = time.time() - start
        print()
        print_success(f"Extraction completed in {styled_text(f'{extraction_time:.1f}s', Color.BRIGHT_WHITE)}")
        guard_write("EXTRACTION_COMPLETE")
        if new_pins:
            print_success(f"Found {styled_text(str(len(new_pins)), Color.BRIGHT_GREEN)} new pins")


        # ================= DOWNLOAD PHASE =================

        BOARD_DOWNLOAD_DIR = os.path.join(DOWNLOADS_DIR, f"{board_id}__{board_name}")
        os.makedirs(BOARD_DOWNLOAD_DIR, exist_ok=True)

        def get_downloaded_ids():
            return {
                os.path.splitext(f)[0] 
                for f in os.listdir(BOARD_DOWNLOAD_DIR)
                if os.path.splitext(f)[1].lower() in {".jpg",".jpeg",".png",".webp"}
            }

        downloaded_ids = get_downloaded_ids()
        new_ids = {p["id"] for p in new_pins}
        pending_previous_ids = history_ids - downloaded_ids - new_ids
        pending_new_ids = new_ids - downloaded_ids

        def pins_by_ids(ids):
            result = []
            new_lookup = {p["id"]: p for p in new_pins}
            
            for pid in ids:
                if pid in new_lookup:
                    result.append(new_lookup[pid])
                else:
                    # Previous pin — pull from history_map
                    result.append({
                        "id": pid,
                        "url": f"https://www.pinterest.com/pin/{pid}/",
                        "img_url": history_map[pid]
                    })
            return result

        download_queue = []

        if pending_new_ids:
            print_section("New Pins Detected", "📍")
            for p in new_pins:
                print(p["url"])

            if pending_previous_ids:
                print()
                print_warning(f"{len(pending_previous_ids)} previous + {len(pending_new_ids)} new pins not downloaded")
                print(f"  {styled_text('b', Color.BRIGHT_GREEN)} → Download both (all {len(pending_previous_ids) + len(pending_new_ids)} pins)")
                print(f"  {styled_text('p', Color.BRIGHT_YELLOW)} → Download previous only ({len(pending_previous_ids)} pins)")
                print(f"  {styled_text('n', Color.BRIGHT_CYAN)} → Download new only ({len(pending_new_ids)} pins)")
                print(f"  {styled_text('s', Color.BRIGHT_RED)} → Skip")
                
                c = ask_choice("Choice: ", {"b","p","n","s"})
                if c in {"b","p"}:
                    download_queue += pins_by_ids(pending_previous_ids)
                if c in {"b","n"}:
                    download_queue += pins_by_ids(pending_new_ids)
            else:
                if ask_choice(f"Download {len(pending_new_ids)} new pins? (y/n): ", {"y","n"}) == "y":
                    download_queue += pins_by_ids(pending_new_ids)

        elif pending_previous_ids:
            print_section("Download Status", "💾")
            print_warning(f"{len(pending_previous_ids)} previous pins were not downloaded")
        
            if ask_choice(f"Download now? (y/n): ", {"y","n"}) == "y":
                download_queue += pins_by_ids(pending_previous_ids)

        def download_image(p):
            url, pid = p["img_url"], p["id"]
            if not url:
                print_error("No url found! Pin removed by creater.")
                return "invalid"
            ext = url.split(".")[-1].split("?")[0].lower()
            if ext not in {"jpg","jpeg","png","webp"}:
                ext = "jpg"
            path = os.path.join(BOARD_DOWNLOAD_DIR, f"{pid}.{ext}")
            tmp = path + ".part"
            if os.path.exists(path):
                return "skipped"
            try:
                r = requests.get(url, headers=HEADERS, timeout=15, stream=True)
                if r.status_code != 200:
                    return "failed"
                with open(tmp, "wb") as f:
                    for c in r.iter_content(8192):
                        if c:
                            f.write(c)
                os.replace(tmp, path)
                return "ok"
            except:
                if os.path.exists(tmp):
                    os.remove(tmp)
                return "failed"

        if download_queue:
            print_section("Downloading Images", "⬇️")
            print_info(f"Downloading {len(download_queue)} image(s)...")
            
            stats = {"ok":0,"skipped":0,"failed":0,"invalid":0}
            download_start = time.time()
            completed = 0
            
            with ThreadPoolExecutor(max_workers=5) as ex:
                futures = []
                for p in download_queue:
                    futures.append(ex.submit(download_image, p))
                    time.sleep(0.1)  # Added Rate Limiting
                    
                for f in as_completed(futures):
                    stats[f.result()] += 1
                    completed += 1
                    
                    # Progress bar
                    print(f"\r  {progress_bar(completed, len(download_queue))}", end="", flush=True)

            print(f"\r  {progress_bar(completed, len(download_queue))}")
        
            download_time = time.time() - download_start
            print()
            print_success(f"Download completed in {styled_text(f'{download_time:.1f}s', Color.BRIGHT_WHITE)}")
            print()
            print(styled_text("  Summary:", Color.BRIGHT_WHITE, Color.BOLD))
            print(f"    {styled_text('✓', Color.BRIGHT_GREEN)} Downloaded: {styled_text(str(stats['ok']), Color.BRIGHT_GREEN)}")
            if stats['skipped'] > 0:
                print(f"    {styled_text('○', Color.BRIGHT_YELLOW)} Skipped:    {styled_text(str(stats['skipped']), Color.BRIGHT_YELLOW)}")
            if stats['failed'] > 0:
                print(f"    {styled_text('✗', Color.BRIGHT_RED)} Failed:     {styled_text(str(stats['failed']), Color.BRIGHT_RED)}")
            if stats['invalid'] > 0:
                print(f"    {styled_text('!', Color.BRIGHT_RED)} Invalid:    {styled_text(str(stats['invalid']), Color.BRIGHT_RED)}")
            
            print()
            print(styled_text(f"  📁 Saved to: {BOARD_DOWNLOAD_DIR}", Color.BRIGHT_CYAN))

        #Clear
        if not new_pins:
            downloaded_ids = get_downloaded_ids()
            pending_after = history_ids - downloaded_ids

            if not pending_after:
                print()
                print_success("All pins are up to date and downloaded! ✨")
                
        guard_write("DOWNLOAD_HANDLED")        
        print()
        print(styled_text("─" * 50, Color.DIM))
        print(styled_text("  Done! Thank you for using PinRecon Pin Extractor", Color.BRIGHT_CYAN))
        print(styled_text("─" * 50, Color.DIM))
        print()
        safe_exit()

    except KeyboardInterrupt:
        handle_keyboard_interrupt(last_state)
   
        
if __name__ == "__main__":
    main()
