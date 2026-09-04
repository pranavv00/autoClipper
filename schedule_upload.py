#!/usr/bin/env python3
"""
Instagram Reels Auto-Scheduler — Open instagram.com in YOUR Chrome browser,
create a post, upload each video clip, add caption, set schedule time via
Advanced Settings, and repeat for all clips. No waiting between uploads!

===================================================================================
HOW IT WORKS
===================================================================================

1. Scans output/ folder for video clips (clip_001.mp4, clip_002.mp4, …)
2. Opens YOUR Chrome browser (with your existing login)
3. For each clip (back-to-back, no waiting):
   a) Goes to instagram.com
   b) Clicks Create (+) → uploads the video
   c) Clicks through to caption screen
   d) Adds caption (e.g. "My Video - Part 1 🎬")
   e) Opens Advanced Settings → Schedule → sets date/time
   f) Clicks Schedule
4. Script finishes in minutes — Instagram publishes at scheduled times!

===================================================================================
USAGE
===================================================================================

    python schedule_upload.py --dry-run          # Preview schedule only
    python schedule_upload.py                     # Upload & schedule all clips
    python schedule_upload.py --limit 1           # Test with just 1 clip
    python schedule_upload.py --interval 60       # 60 min between posts (default)
    python schedule_upload.py --caption "{title} Part {part} 🔥"
    python schedule_upload.py --reset             # Re-upload everything

===================================================================================
IMPORTANT
===================================================================================

- Close Chrome before running! (Selenium needs exclusive Chrome profile access)
- You must be logged into Instagram in Chrome already
- Your account must be a Professional (Business/Creator) account for scheduling

===================================================================================
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Time between each scheduled Reel publish (in seconds). 3600 = 1 hour
UPLOAD_INTERVAL: int = 3600

# Caption template — {title} = video folder name, {part} = clip number
CAPTION_TEMPLATE: str = """{title} - Part {part} 🎬

Taarak Mehta Ka Ooltah Chashmah (commonly abbreviated as TMKOC) is India's longest-running television sitcom. Produced by Asit Kumarr Modi under Neela Tele Films, the show made its television debut on July 28, 2008, broadcasting on Sony SAB. Over the years, the show has surpassed massive milestones, celebrating over 18 years on air and broadcasting well past 4,800 episodes, cementing its status as a cornerstone of Indian pop culture.

The plot is set in the fictional Gokuldham Co-operative Housing Society in Mumbai, where a diverse community of families from different religious, regional, and economic backgrounds live together like one large, extended family. The show focuses on their comedic day-to-day situations and promotes unity, problem-solving, and community values. The narrative primarily revolves around the central character, Jethalal Champaklal Gada (played by Dilip Joshi), a quirky electronics businessman who constantly finds himself in bizarre and humorous predicaments. With the help of his close friend and "fire brigade," the narrator Taarak Mehta, Jethalal solves his problems, concluding each episode with a lighthearted social message or moral lesson that appeals to viewers of all generations.

#TMKOC #TaarakMehtaKaOoltahChashmah #Jethalal #GokuldhamSociety #SonySAB #IndianComedy #Reels"""

# Folder where clips live (relative to this script)
OUTPUT_DIR: str = "output"

# How long after running the script the FIRST reel should publish (seconds)
FIRST_PUBLISH_DELAY: int = 1800  # 30 minutes from now (at least 25 min)

# Upload progress tracking file
UPLOAD_LOG_FILE: str = "upload_log.json"

# Supported video file extensions
SUPPORTED_EXTENSIONS: set[str] = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# Browser wait timeout (seconds)
BROWSER_TIMEOUT: int = 60

# Delay between browser actions (seconds) — human-like
ACTION_DELAY: float = 2.0

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _log(message: str, *, indent: int = 0) -> None:
    prefix = "  " * indent
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {prefix}{message}", flush=True)


def _log_separator() -> None:
    print("─" * 60, flush=True)


def natural_sort_key(path: Path) -> list:
    """Natural sort: clip_1, clip_2, ..., clip_10."""
    text = path.stem.lower()
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text)]


def human_delay(base: float = ACTION_DELAY, variance: float = 1.0) -> None:
    """Sleep for a human-like random duration."""
    import random
    time.sleep(base + random.uniform(0, variance))


# ─────────────────────────────────────────────────────────────────────────────
# CLIP DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────


def discover_clips(output_dir: Path) -> list[dict]:
    """
    Scan the output directory for video subfolders and their clips.
    Returns a flat, ordered list of clip dicts.
    """
    all_clips: list[dict] = []

    if not output_dir.is_dir():
        _log(f"✖  Output directory not found: {output_dir}")
        return all_clips

    for folder in sorted(output_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_") or folder.name.startswith("."):
            continue

        clips = [
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        if not clips:
            continue

        clips.sort(key=natural_sort_key)

        for idx, clip_path in enumerate(clips, start=1):
            match = re.search(r"(\d+)", clip_path.stem)
            part_num = int(match.group(1)) if match else idx

            all_clips.append({
                "title": folder.name,
                "part": part_num,
                "path": clip_path,
                "clip_name": clip_path.name,
            })

    return all_clips


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD LOG (RESUME TRACKING)
# ─────────────────────────────────────────────────────────────────────────────


def load_upload_log(log_path: Path) -> dict:
    if log_path.exists():
        try:
            with open(log_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_upload_log(log_path: Path, log_data: dict) -> None:
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2, default=str)


def is_clip_uploaded(log_data: dict, clip_path: str) -> bool:
    return clip_path in log_data.get("uploaded", {})


def mark_clip_uploaded(log_data: dict, clip_path: str, caption: str, scheduled: str) -> None:
    if "uploaded" not in log_data:
        log_data["uploaded"] = {}
    log_data["uploaded"][clip_path] = {
        "caption": caption,
        "scheduled_for": scheduled,
        "uploaded_at": datetime.now().isoformat(),
    }


def get_latest_scheduled_time(log_data: dict) -> datetime | None:
    """Find the latest scheduled_for datetime from upload_log."""
    latest: datetime | None = None
    for entry in log_data.get("uploaded", {}).values():
        sched_str = entry.get("scheduled_for")
        if sched_str:
            try:
                dt = datetime.fromisoformat(sched_str)
                if latest is None or dt > latest:
                    latest = dt
            except (ValueError, TypeError):
                pass
    return latest


# ─────────────────────────────────────────────────────────────────────────────
# BROWSER SETUP
# ─────────────────────────────────────────────────────────────────────────────


def get_chrome_profile_path() -> str:
    """
    Dedicated Chrome automation directory on macOS.
    Avoids Chrome's 'DevTools remote debugging requires a non-default data directory' restriction
    and allows regular Chrome to remain open without conflicting.
    """
    profile_dir = Path.home() / "Library" / "Application Support" / "Google" / "Chrome-Automation"
    profile_dir.mkdir(parents=True, exist_ok=True)
    return str(profile_dir)


def kill_automation_chrome() -> None:
    """Close any leftover automation Chrome instances so profile lock is released."""
    import subprocess
    try:
        subprocess.run(
            ["pkill", "-f", "Chrome-Automation"],
            capture_output=True, timeout=5,
        )
        time.sleep(1)
    except Exception:
        pass


def create_driver():
    """Create a Selenium Chrome WebDriver using the automation profile."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()

    # Use dedicated automation profile (keeps login session permanently)
    profile_path = get_chrome_profile_path()
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument("--profile-directory=Default")

    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    # Anti-detection
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )

    return driver


def ensure_instagram_logged_in(driver) -> bool:
    """
    Check if the user is logged into Instagram.
    If not, prompt the user in terminal and wait for them to log in in the browser window.
    Session is automatically preserved in the Chrome-Automation profile for all future runs.
    """
    from selenium.webdriver.common.by import By
    import subprocess

    _log("Checking Instagram login status...")
    driver.get("https://www.instagram.com/")
    time.sleep(4)

    # Bring Chrome window to front on macOS
    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome" to activate'],
            capture_output=True, timeout=3,
        )
    except Exception:
        pass

    def is_logged_in():
        try:
            _ = driver.current_window_handle
        except Exception:
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[-1])
            else:
                return False

        try:
            if driver.find_elements(By.NAME, "username"):
                return False
            if "/accounts/login" in driver.current_url:
                return False
            create_els = driver.find_elements(By.XPATH,
                "//*[contains(@aria-label, 'New post') or contains(@aria-label, 'Create') or text()='Create']"
            )
            for el in create_els:
                label = (el.get_attribute("aria-label") or "").lower()
                text = (el.text or "").lower()
                if "create new account" in label or "create new account" in text:
                    continue
                return True
            nav_icons = driver.find_elements(By.XPATH,
                "//*[contains(@aria-label, 'Home') or contains(@aria-label, 'Direct') or contains(@aria-label, 'Explore') or contains(@aria-label, 'Profile')]"
            )
            if len(nav_icons) >= 2:
                return True
        except Exception:
            return False
        return False

    if is_logged_in():
        _log("✓ Already logged in to Instagram!")
        return True

    print("\n" + "=" * 65)
    _log("👉 PLEASE LOG IN TO INSTAGRAM IN THE CHROME WINDOW NOW")
    _log("   1. A Google Chrome window is open on your screen.")
    _log("   2. Log in with your Instagram credentials (and 2FA if enabled).")
    _log("   3. The script will automatically detect your login and proceed!")
    _log("   (Your login will be saved permanently for all future runs)")
    print("=" * 65 + "\n")

    for _ in range(150):  # Wait up to 5 minutes
        time.sleep(2)
        try:
            if is_logged_in():
                _log("✓ Login successful! Instagram is ready.")
                time.sleep(2)
                return True
        except Exception:
            pass

    _log("✖ Login timed out after 5 minutes.")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# INSTAGRAM UPLOAD + SCHEDULE FLOW
# ─────────────────────────────────────────────────────────────────────────────


def upload_and_schedule_reel(driver, clip: dict) -> bool:
    """
    Upload a single video clip as a Reel on instagram.com and schedule it:
      1. Go to instagram.com
      2. Click Create (+)
      3. Upload the video file
      4. Click Next → Next (past crop/filter screens)
      5. Type caption
      6. Open "Advanced settings" → toggle "Schedule" → set date/time
      7. Click "Schedule"

    Returns True on success, False on failure.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        ElementClickInterceptedException,
        StaleElementReferenceException,
    )
    from selenium.webdriver.common.action_chains import ActionChains

    caption: str = clip["caption"]
    video_path: str = str(clip["path"].resolve())
    scheduled_time: datetime = clip["scheduled_time"]

    try:
        # Ensure driver is attached to the active browser window
        try:
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[-1])
        except Exception:
            pass

        # ── Step 1: Go to Instagram ─────────────────────────────────────
        _log("Opening instagram.com...", indent=1)
        driver.get("https://www.instagram.com/")
        human_delay(3.0, 2.0)

        # Dismiss any popups
        _dismiss_popups(driver)

        # ── Step 2: Click "Create" (+) ──────────────────────────────────
        _log("Clicking Create (+)...", indent=1)

        create_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH,
                "//*[contains(@aria-label, 'New post') or contains(@aria-label, 'Create')] | "
                "//a[.//span[text()='Create']] | "
                "//div[@role='button'][.//span[text()='Create']]"
            ))
        )
        create_btn.click()
        human_delay(1.5)

        # Check for 'Post' sub-menu item
        try:
            post_item = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//a[.//span[text()='Post'] or text()='Post'] | "
                    "//div[@role='button'][.//span[text()='Post'] or text()='Post'] | "
                    "//span[text()='Post']"
                ))
            )
            post_item.click()
            human_delay(1.5)
        except TimeoutException:
            pass

        _log("✓ Create dialog opened", indent=1)

        # ── Step 3: Upload the video file ───────────────────────────────
        _log(f"Uploading: {clip['clip_name']}...", indent=1)

        file_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
        )
        file_input.send_keys(video_path)
        _log("✓ Video file selected", indent=1)

        # Wait for video to process
        _log("⏳ Waiting for video to process...", indent=1)
        human_delay(5.0, 2.0)

        # Dismiss any ratio / reel alert popup
        try:
            ok_btn = driver.find_element(By.XPATH,
                "//button[text()='OK' or .//div[text()='OK']] | "
                "//div[@role='button' and text()='OK']"
            )
            ok_btn.click()
            human_delay(1.0)
        except NoSuchElementException:
            pass

        # ── Step 4: Click Next → Next ───────────────────────────────────
        # Next #1: past crop screen
        if not _click_next_button(driver):
            _log("✖  Could not pass crop screen", indent=1)
            driver.save_screenshot("/tmp/ig_debug_crop.png")
            return False
        human_delay(3.0, 1.0)

        # Next #2: past filter/edit screen
        if not _click_next_button(driver):
            _log("✖  Could not pass edit screen", indent=1)
            driver.save_screenshot("/tmp/ig_debug_filter.png")
            return False
        human_delay(3.0, 1.0)

        # ── Step 5: Type caption ────────────────────────────────────────
        _log("Writing caption...", indent=1)

        try:
            caption_area = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//div[@role='textbox' and ("
                    "contains(@aria-label, 'caption') or "
                    "contains(@aria-label, 'Write a caption') or "
                    "contains(@aria-label, 'Write')"
                    ")] | "
                    "//textarea[contains(@aria-label, 'caption') or "
                    "contains(@placeholder, 'Write a caption')]"
                ))
            )
            caption_area.click()
            human_delay(0.5)

            # Insert caption via JS for speed and emojis/newlines support
            driver.execute_script("""
                let el = arguments[0];
                let text = arguments[1];
                el.focus();
                document.execCommand('insertText', false, text);
            """, caption_area, caption)

            _log("✓ Caption written", indent=1)
        except Exception as e:
            _log(f"⚠  Caption insertion error: {e}", indent=1)

        human_delay(1.5)

        # ── Step 6: Toggle Schedule content & Set DateTime ──────────────
        _log(f"Setting schedule: {scheduled_time.strftime('%b %d, %I:%M %p')}...", indent=1)

        # Scroll down dialog sidebar to bring Schedule content into view
        driver.execute_script("""
            let el = Array.from(document.querySelectorAll('span, div')).find(e => e.innerText && e.innerText.trim() === 'Schedule content');
            if (el) {
                el.scrollIntoView({block: 'center'});
            } else {
                let dialog = document.querySelector('div[role=dialog]');
                if (dialog) dialog.scrollTop = dialog.scrollHeight;
            }
        """)
        human_delay(1.0)

        # Toggle Schedule switch on
        toggled = driver.execute_script("""
            let span = Array.from(document.querySelectorAll('span, div')).find(e => e.innerText && e.innerText.trim() === 'Schedule content');
            if (!span) return false;
            let row = span.closest('div');
            while (row && !row.querySelector('input[type=checkbox], [role=switch]')) {
                row = row.parentElement;
            }
            if (!row) return false;
            let sw = row.querySelector('input[type=checkbox], [role=switch]');
            if (sw) {
                let checked = sw.getAttribute('aria-checked') === 'true' || sw.checked;
                if (!checked) {
                    sw.click();
                }
                return true;
            }
            return false;
        """)

        if not toggled:
            try:
                sw = driver.find_element(By.XPATH, "//input[@role='switch'][ancestor::div[contains(., 'Schedule content')]]")
                if sw.get_attribute("aria-checked") != "true":
                    driver.execute_script("arguments[0].click();", sw)
            except Exception:
                pass

        _log("✓ Schedule content toggled on", indent=1)
        human_delay(1.5)

        # Set date and time
        _set_schedule_datetime(driver, scheduled_time)
        human_delay(1.5)

        # ── Step 7: Click "Schedule" button ─────────────────────────────
        _log("Clicking Schedule...", indent=1)

        from selenium.webdriver.common.action_chains import ActionChains

        schedule_btn = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH,
                "//*[@role='button' and normalize-space()='Schedule'] | "
                "//button[normalize-space()='Schedule']"
            ))
        )
        try:
            ActionChains(driver).move_to_element(schedule_btn).click().perform()
            _log("✓ Schedule button clicked (via ActionChains)!", indent=1)
        except Exception:
            try:
                schedule_btn.click()
                _log("✓ Schedule button clicked (native)!", indent=1)
            except Exception:
                driver.execute_script("arguments[0].click();", schedule_btn)
                _log("✓ Schedule button clicked (via JS)!", indent=1)

        # ── Step 8: Wait for genuine confirmation ───────────────────────
        _log("⏳ Waiting for Instagram to process and confirm schedule...", indent=1)

        # 1. Wait for "Scheduling" dialog to appear (confirms upload started)
        try:
            WebDriverWait(driver, 15).until(
                lambda d: any("scheduling" in (e.text or "").lower()
                              for e in d.find_elements(By.XPATH, "//div[@role='dialog']"))
            )
            _log("⏳ Uploading and encoding video on Instagram...", indent=1)
        except TimeoutException:
            pass

        # 2. Wait for final confirmation: "Reel scheduled" or "Your reel has been scheduled"
        confirmed = False
        try:
            WebDriverWait(driver, 120).until(
                lambda d: any(
                    ("scheduled" in (e.text or "").lower() or "your reel" in (e.text or "").lower())
                    and "scheduling" not in (e.text or "").lower()
                    for e in d.find_elements(By.XPATH, "//div[@role='dialog']")
                )
            )
            confirmed = True
        except TimeoutException:
            _log("✖  Timed out waiting for 'Reel scheduled' confirmation dialog", indent=1)

        if confirmed:
            _log("✅ Reel scheduled successfully!", indent=1)
            # Click "Done" button to cleanly close modal
            try:
                done_btn = driver.find_element(By.XPATH,
                    "//div[@role='dialog']//*[normalize-space()='Done' and (@role='button' or ancestor::*[@role='button'] or ancestor::button)]"
                )
                ActionChains(driver).move_to_element(done_btn).click().perform()
                _log("✓ Closed confirmation modal", indent=1)
            except Exception:
                pass
            human_delay(2.0)
            return True
        else:
            try:
                driver.save_screenshot("/tmp/ig_debug_schedule_failed.png")
                _log("  Screenshot saved: /tmp/ig_debug_schedule_failed.png", indent=1)
            except Exception:
                pass
            return False

    except Exception as exc:
        _log(f"✖  Unexpected error: {exc}", indent=1)
        try:
            driver.save_screenshot("/tmp/ig_debug_error.png")
            _log("  Screenshot: /tmp/ig_debug_error.png", indent=1)
        except Exception:
            pass
        return False


def _dismiss_popups(driver) -> None:
    """Dismiss common Instagram popups."""
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import NoSuchElementException

    for text in ["Not Now", "Not now", "Decline", "Cancel"]:
        try:
            btn = driver.find_element(By.XPATH,
                f"//button[text()='{text}'] | //button[.//div[text()='{text}']]"
            )
            btn.click()
            human_delay(1.0)
        except NoSuchElementException:
            continue

    try:
        btn = driver.find_element(By.XPATH,
            "//button[contains(text(), 'Allow') and contains(text(), 'cookie')]"
            " | //button[contains(text(), 'Accept')]"
        )
        btn.click()
        human_delay(1.0)
    except NoSuchElementException:
        pass


def _click_next_button(driver) -> bool:
    """Find and click the 'Next' button."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    try:
        next_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH,
                "//*[@role='button' and normalize-space()='Next'] | "
                "//button[normalize-space()='Next'] | "
                "//*[normalize-space(text())='Next' and (@role='button' or ancestor::*[@role='button'])]"
            ))
        )
        driver.execute_script("arguments[0].click();", next_btn)
        _log("✓ Clicked Next", indent=1)
        return True
    except TimeoutException:
        # Fallback with javascript
        try:
            clicked = driver.execute_script("""
                let el = Array.from(document.querySelectorAll('[role=button], button, div, span'))
                    .find(e => e.innerText && e.innerText.trim() === 'Next');
                if (el) { el.click(); return true; }
                return false;
            """)
            if clicked:
                _log("✓ Clicked Next (via JS)", indent=1)
                return True
        except Exception:
            pass
        _log("⚠  'Next' button not found", indent=1)
        return False


def _set_schedule_datetime(driver, scheduled_time: datetime) -> None:
    """Set the date and time in Instagram's schedule picker."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # 1. Set Time (Hours and Minutes spinbutton inputs)
    try:
        h_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@aria-label='Hours']"))
        )
        h_input.click()
        h_input.send_keys(Keys.COMMAND + "a")
        h_input.send_keys(Keys.BACKSPACE)
        h_input.send_keys(f"{scheduled_time.hour:02d}")
        time.sleep(0.3)

        m_input = driver.find_element(By.XPATH, "//input[@aria-label='Minutes']")
        m_input.click()
        m_input.send_keys(Keys.COMMAND + "a")
        m_input.send_keys(Keys.BACKSPACE)
        m_input.send_keys(f"{scheduled_time.minute:02d}")
        time.sleep(0.3)
        _log(f"✓ Time set to {scheduled_time.strftime('%I:%M %p')}", indent=2)
    except Exception as exc:
        _log(f"⚠  Error setting time input: {exc}", indent=2)

    # 2. Set Date (if scheduled for tomorrow or a future date)
    now = datetime.now()
    if scheduled_time.date() != now.date():
        try:
            _log(f"Setting date to {scheduled_time.strftime('%b %d')}...", indent=2)
            # Click date button to open calendar
            driver.execute_script("""
                let dateSpan = Array.from(document.querySelectorAll('*')).find(e => e.innerText && e.innerText.trim() === 'Date');
                if (dateSpan) {
                    let btn = dateSpan.parentElement.querySelector('[role=button]');
                    if (btn) btn.click();
                }
            """)
            time.sleep(1.0)

            # Click target day in calendar
            target_day_str = str(scheduled_time.day)
            driver.execute_script("""
                let day = arguments[0];
                let cells = Array.from(document.querySelectorAll('[role=dialog] span, [role=dialog] div, [role=dialog] button'))
                    .filter(e => e.innerText && e.innerText.trim() === day);
                if (cells.length > 0) {
                    cells[cells.length - 1].click();
                }
            """, target_day_str)
            time.sleep(1.0)
            _log(f"✓ Date set to {scheduled_time.strftime('%b %d')}", indent=2)
        except Exception as exc:
            _log(f"⚠  Error setting date: {exc}", indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="🎬 Instagram Reels Auto-Scheduler (via instagram.com)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python schedule_upload.py --dry-run          # Preview schedule
    python schedule_upload.py                     # Upload & schedule all
    python schedule_upload.py --limit 1           # Test with 1 clip
    python schedule_upload.py --interval 60       # 60 min between posts
    python schedule_upload.py --delay 20          # First post 20 min from now
        """,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview schedule without uploading")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max clips to upload (0 = all)")
    parser.add_argument("--interval", type=int, default=UPLOAD_INTERVAL // 60,
                        help=f"Minutes between posts (default: {UPLOAD_INTERVAL // 60})")
    parser.add_argument("--delay", type=int, default=FIRST_PUBLISH_DELAY // 60,
                        help=f"Minutes until first post publishes (default: {FIRST_PUBLISH_DELAY // 60})")
    parser.add_argument("--after-last", type=float, default=3.0,
                        help="Hours after the last scheduled reel in upload_log to begin next schedule (default: 3.0)")
    parser.add_argument("--start-time", type=str, default=None,
                        help="Explicit start datetime (e.g. '2026-09-05 08:24' or ISO format)")
    parser.add_argument("--caption", type=str, default=CAPTION_TEMPLATE,
                        help=f'Caption template (default: "{CAPTION_TEMPLATE}")')
    parser.add_argument("--reset", action="store_true",
                        help="Reset upload log, re-upload everything")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    interval_seconds = args.interval * 60
    first_delay_seconds = args.delay * 60

    _log_separator()
    _log("🎬  Instagram Reels Auto-Scheduler")
    _log(f"    Method         : instagram.com (Chrome browser)")
    _log(f"    Interval       : {args.interval} min between posts")
    _log(f"    First publish  : {args.delay} min from now")
    _log(f"    Caption format : {args.caption}")
    _log(f"    Output folder  : {OUTPUT_DIR}/")
    if args.dry_run:
        _log(f"    Mode           : 🏜️  DRY RUN")
    _log_separator()

    # 1. Resolve paths
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / OUTPUT_DIR
    log_path = script_dir / UPLOAD_LOG_FILE

    # 2. Discover clips
    clips = discover_clips(output_dir)

    if not clips:
        _log("\n✖  No clips found in output/. Run split_videos.py first.")
        sys.exit(0)

    video_count = len(set(c["title"] for c in clips))
    _log(f"\nFound {len(clips)} clip(s) across {video_count} video(s)\n")

    # 3. Load upload log
    if args.reset and log_path.exists():
        log_path.unlink()
        _log("🔄 Upload log reset\n")

    log_data = load_upload_log(log_path)

    # 4. Filter already-uploaded clips
    pending = [c for c in clips if not is_clip_uploaded(log_data, str(c["path"]))]

    if not pending:
        _log("✅ All clips already uploaded! Use --reset to re-upload.")
        sys.exit(0)

    skipped = len(clips) - len(pending)
    if skipped > 0:
        _log(f"⏩ Skipping {skipped} already-uploaded clip(s)\n")

    if args.limit > 0:
        pending = pending[:args.limit]

    # 5. Calculate schedule times
    now = datetime.now()
    min_allowed_time = now + timedelta(seconds=first_delay_seconds)
    latest_scheduled = get_latest_scheduled_time(log_data)

    if latest_scheduled:
        _log(f"📌 Last scheduled reel in log : {latest_scheduled.strftime('%b %d, %I:%M %p')}")

    if args.start_time:
        first_publish = datetime.fromisoformat(args.start_time).replace(second=0, microsecond=0)
        _log(f"⏰ Using explicit start time   : {first_publish.strftime('%b %d, %I:%M %p')}")
    elif latest_scheduled is not None and args.after_last is not None:
        candidate_time = (latest_scheduled + timedelta(hours=args.after_last)).replace(second=0, microsecond=0)
        if candidate_time > min_allowed_time:
            first_publish = candidate_time
            _log(f"⏰ Scheduling start set to {args.after_last:g}h after last reel: {first_publish.strftime('%b %d, %I:%M %p')}")
        else:
            first_publish = min_allowed_time.replace(second=0, microsecond=0)
            _log(f"⏰ Candidate time ({candidate_time.strftime('%b %d, %I:%M %p')}) is earlier than min delay. Using: {first_publish.strftime('%b %d, %I:%M %p')}")
    else:
        first_publish = min_allowed_time.replace(second=0, microsecond=0)
        _log(f"⏰ Starting at {args.delay}m from now: {first_publish.strftime('%b %d, %I:%M %p')}")

    for i, clip in enumerate(pending):
        clip["scheduled_time"] = first_publish + timedelta(seconds=i * interval_seconds)
        clip["caption"] = args.caption.format(
            title=clip["title"].replace("_", " ").replace("-", " ").title(),
            part=clip["part"],
        )

    # 6. Display schedule
    _log("📅 Schedule Preview:")
    _log_separator()

    current_title = None
    for i, clip in enumerate(pending, start=1):
        if clip["title"] != current_title:
            if current_title is not None:
                print()
            current_title = clip["title"]
            _log(f"📁 {clip['title'].replace('_', ' ').title()}")

        time_str = clip["scheduled_time"].strftime("%b %d, %I:%M %p")
        _log(f"   {i:>3}. Part {clip['part']:<3}  →  {time_str}  ({clip['clip_name']})")

    print()
    _log_separator()
    total = pending[-1]["scheduled_time"] - pending[0]["scheduled_time"]
    _log(f"📊 {len(pending)} Reels | Span: {total} | Last: {pending[-1]['scheduled_time'].strftime('%I:%M %p')}")
    _log_separator()

    # 7. Dry run stop
    if args.dry_run:
        print()
        _log("🏜️  Dry run — no uploads. Remove --dry-run to go live.")
        sys.exit(0)

    # 8. Clean up any leftover automation Chrome instance
    print()
    kill_automation_chrome()

    # 9. Open browser and upload everything
    print()
    _log("🌐 Opening Chrome via Selenium...")

    driver = None
    try:
        driver = create_driver()
        _log("✓ Chrome opened with automation profile\n")

        # Verify Instagram login status
        if not ensure_instagram_logged_in(driver):
            _log("✖ Cannot proceed without being logged in to Instagram.")
            return

        success = 0
        fail = 0

        for i, clip in enumerate(pending, start=1):
            _log_separator()
            sched_str = clip["scheduled_time"].strftime("%I:%M %p")
            _log(f"[{i}/{len(pending)}] {clip['caption']}  →  scheduled for {sched_str}")

            result = upload_and_schedule_reel(driver, clip)

            if result:
                success += 1
                mark_clip_uploaded(
                    log_data, str(clip["path"]),
                    clip["caption"],
                    clip["scheduled_time"].isoformat(),
                )
                save_upload_log(log_path, log_data)
                _log(f"✅ ({success}/{len(pending)}) scheduled")
            else:
                fail += 1
                _log(f"❌ Failed — continuing to next clip...")

            # Brief pause between uploads
            if i < len(pending):
                _log("⏳ Pausing 10s before next upload...")
                time.sleep(10)

        # Summary
        print()
        _log_separator()
        _log("✅ All done!")
        _log(f"    Scheduled : {success} Reel(s)")
        _log(f"    Failed    : {fail} Reel(s)")
        if success > 0:
            _log(f"    First post: {pending[0]['scheduled_time'].strftime('%b %d, %I:%M %p')}")
            _log(f"    Last post : {pending[-1]['scheduled_time'].strftime('%b %d, %I:%M %p')}")
        _log_separator()
        _log("\n🎉 Instagram will publish them automatically at the scheduled times!")

        if fail > 0:
            _log("💡 Re-run the script to retry failed uploads.\n")

    except KeyboardInterrupt:
        print()
        _log("\n⚠  Interrupted! Progress saved. Re-run to resume.")
    except Exception as exc:
        _log(f"\n✖  Fatal error: {exc}")
        _log("   Progress saved. Re-run to resume.")
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
