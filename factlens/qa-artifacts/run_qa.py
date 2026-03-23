from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Callable

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import ChromeOptions, EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


APP_URL = "http://127.0.0.1:5173"
ARTIFACT_ROOT = Path(__file__).resolve().parent
SCREENSHOT_DIR = ARTIFACT_ROOT / "screenshots"
RESULTS_DIR = ARTIFACT_ROOT / "results"


def ensure_dirs() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def build_driver():
    last_error = None

    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1440,1600")
    chrome_options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    try:
        return webdriver.Chrome(options=chrome_options), "chrome"
    except WebDriverException as exc:
        last_error = exc

    edge_options = EdgeOptions()
    edge_options.use_chromium = True
    edge_options.add_argument("--headless=new")
    edge_options.add_argument("--window-size=1440,1600")
    edge_options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    try:
        return webdriver.Edge(options=edge_options), "edge"
    except WebDriverException as exc:
        last_error = exc

    raise RuntimeError(f"Could not start Chrome or Edge: {last_error}")


def wait_for_text(driver, text: str, timeout: int = 60):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, f"//*[contains(normalize-space(.), {json.dumps(text)})]"))
    )


def wait_for_clickable(driver, xpath: str, timeout: int = 30):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )


def click_text_button(driver, label: str, timeout: int = 30):
    button = wait_for_clickable(
        driver,
        f"//button[contains(normalize-space(.), {json.dumps(label)})] | //a[contains(normalize-space(.), {json.dumps(label)})]",
        timeout=timeout,
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
    time.sleep(0.2)
    try:
        button.click()
    except Exception:  # noqa: BLE001
        driver.execute_script("arguments[0].click();", button)
    return button


def save_screenshot(driver, name: str) -> None:
    driver.save_screenshot(str(SCREENSHOT_DIR / f"{name}.png"))


def layout_state(driver) -> dict:
    return driver.execute_script(
        """
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const root = document.documentElement;
        const overflowX = root.scrollWidth - viewportWidth;
        const offenders = Array.from(document.querySelectorAll('body *'))
          .map((node) => {
            const rect = node.getBoundingClientRect();
            if (!rect.width || !rect.height) return null;
            const text = (node.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
            if (rect.left < -1 || rect.right > viewportWidth + 1) {
              return {
                tag: node.tagName.toLowerCase(),
                left: Math.round(rect.left),
                right: Math.round(rect.right),
                width: Math.round(rect.width),
                text,
              };
            }
            return null;
          })
          .filter(Boolean)
          .slice(0, 20);
        return {
          viewportWidth,
          viewportHeight,
          scrollWidth: root.scrollWidth,
          scrollHeight: root.scrollHeight,
          overflowX,
          offenders,
        };
        """
    )


def browser_errors(driver) -> list[str]:
    try:
        entries = driver.get_log("browser")
    except Exception:
        return []

    errors = []
    for entry in entries:
        level = str(entry.get("level", "")).upper()
        message = str(entry.get("message", ""))
        if level in {"SEVERE", "ERROR"}:
            errors.append(message)
    return errors


def fetch_with_browser_cookies(driver, url: str) -> dict:
    cookies = driver.get_cookies()
    cookie_header = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
    request = urllib.request.Request(url, headers={"Cookie": cookie_header})
    with urllib.request.urlopen(request, timeout=60) as response:
        return {
            "status": response.status,
            "content_type": response.headers.get("Content-Type", ""),
            "content_disposition": response.headers.get("Content-Disposition", ""),
            "content_length": response.headers.get("Content-Length", ""),
        }


def report_id_from_url(url: str) -> str | None:
    marker = "/report/"
    if marker not in url:
        return None
    return url.split(marker, 1)[1].split("?", 1)[0]


def run_step(summary: dict, name: str, func: Callable[[], None]) -> None:
    try:
        func()
        summary["steps"][name] = {"status": "passed"}
    except Exception as exc:  # noqa: BLE001
        summary["steps"][name] = {"status": "failed", "error": str(exc)}
        summary["issues"].append(f"{name}: {exc}")


def main() -> None:
    ensure_dirs()
    summary: dict = {
        "browser": None,
        "issues": [],
        "steps": {},
        "layout": {},
        "checks": {},
        "console_errors": [],
    }

    driver, browser_name = build_driver()
    summary["browser"] = browser_name
    wait = WebDriverWait(driver, 120)

    def goto(path: str) -> None:
        driver.get(f"{APP_URL}{path}")
        time.sleep(1.5)

    try:
        run_step(summary, "home_desktop", lambda: (
            goto("/"),
            wait_for_text(driver, "Turn any text into an evidence-backed claim report."),
            save_screenshot(driver, "home-desktop"),
            summary["layout"].__setitem__("homeDesktop", layout_state(driver)),
            summary["console_errors"].extend(browser_errors(driver)),
        ))

        def workspace_from_sample() -> None:
            click_text_button(driver, "Clean truth pack")
            wait.until(lambda d: "/workspace" in d.current_url)
            textarea = wait.until(
                EC.presence_of_element_located((By.TAG_NAME, "textarea"))
            )
            value = textarea.get_attribute("value") or ""
            if "Pacific Ocean" not in value:
                raise AssertionError("Sample text did not prefill the workspace.")
            save_screenshot(driver, "workspace-prefill-desktop")
            summary["layout"]["workspacePrefillDesktop"] = layout_state(driver)
            summary["checks"]["workspacePrefillValue"] = value[:120]
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "workspace_prefill_desktop", workspace_from_sample)

        def draft_claims_text() -> None:
            click_text_button(driver, "Review claims first", timeout=60)
            wait_for_text(driver, "Edit the extracted claims before verification", timeout=180)
            claim_badges = driver.find_elements(By.XPATH, "//span[contains(normalize-space(.), 'Claim ')]")
            summary["checks"]["reviewClaimCount"] = len(claim_badges)
            if len(claim_badges) < 3:
                raise AssertionError(f"Expected at least 3 extracted claims, got {len(claim_badges)}.")
            save_screenshot(driver, "claim-review-desktop")
            summary["layout"]["claimReviewDesktop"] = layout_state(driver)
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "claim_review_text_desktop", draft_claims_text)

        def review_panel_controls() -> None:
            click_text_button(driver, "Add claim")
            time.sleep(0.5)
            claim_badges = driver.find_elements(By.XPATH, "//span[contains(normalize-space(.), 'Claim ')]")
            summary["checks"]["reviewClaimCountAfterAdd"] = len(claim_badges)
            click_text_button(driver, "Discard draft")
            time.sleep(0.75)
            headings = driver.find_elements(By.XPATH, "//*[contains(normalize-space(.), 'Edit the extracted claims before verification')]")
            if headings:
                raise AssertionError("Claim review panel did not close after discarding the draft.")
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "claim_review_controls", review_panel_controls)

        def analyze_reviewed_claims() -> None:
            click_text_button(driver, "Review claims first", timeout=60)
            wait_for_text(driver, "Edit the extracted claims before verification", timeout=180)
            click_text_button(driver, "Verify reviewed claims", timeout=60)
            wait.until(lambda d: "/report/" in d.current_url)
            wait_for_text(driver, "Deep review view", timeout=240)
            report_id = report_id_from_url(driver.current_url)
            if not report_id:
                raise AssertionError(f"Could not parse report id from URL {driver.current_url}.")
            summary["checks"]["reportId"] = report_id
            save_screenshot(driver, "report-desktop")
            summary["layout"]["reportDesktop"] = layout_state(driver)
            links = driver.find_elements(By.TAG_NAME, "a")
            link_map = {
                (link.text or "").strip().lower(): link.get_attribute("href")
                for link in links
                if (link.text or "").strip()
            }
            json_link = link_map.get("json")
            pdf_link = link_map.get("pdf")
            if not json_link or not pdf_link:
                raise AssertionError("JSON and PDF export links were not both visible on the report page.")
            summary["checks"]["jsonExport"] = fetch_with_browser_cookies(driver, json_link)
            summary["checks"]["pdfExport"] = fetch_with_browser_cookies(driver, pdf_link)
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "report_generation_desktop", analyze_reviewed_claims)

        def report_actions() -> None:
            click_text_button(driver, "Pin", timeout=30)
            wait_for_text(driver, "Unpin", timeout=30)
            click_text_button(driver, "Archive", timeout=30)
            wait_for_text(driver, "Restore", timeout=30)
            click_text_button(driver, "Restore", timeout=30)
            wait_for_text(driver, "Archive", timeout=30)
            share_buttons = driver.find_elements(By.XPATH, "//button[contains(normalize-space(.), 'Share report') or contains(normalize-space(.), 'Copy share link')]")
            summary["checks"]["shareButtonVisible"] = bool(share_buttons)
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "report_actions", report_actions)

        def history_page() -> None:
            goto("/history")
            wait_for_text(driver, "Saved analyses")
            save_screenshot(driver, "history-desktop")
            summary["layout"]["historyDesktop"] = layout_state(driver)
            summary["checks"]["historyReuseCount"] = len(
                driver.find_elements(By.XPATH, "//*[contains(normalize-space(.), 'Reuse input')]")
            )
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "history_desktop", history_page)

        def demo_page() -> None:
            goto("/demo")
            wait_for_text(driver, "Hackathon walkthrough deck")
            save_screenshot(driver, "demo-desktop")
            summary["layout"]["demoDesktop"] = layout_state(driver)
            summary["checks"]["demoScenarioCount"] = len(
                driver.find_elements(By.XPATH, "//button[contains(normalize-space(.), 'Load scenario')]")
            )
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "demo_desktop", demo_page)

        def methodology_page() -> None:
            goto("/methodology")
            wait_for_text(driver, "How FactLens reaches a verdict")
            save_screenshot(driver, "methodology-desktop")
            summary["layout"]["methodologyDesktop"] = layout_state(driver)
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "methodology_desktop", methodology_page)

        def url_review_flow() -> None:
            goto("/workspace")
            click_text_button(driver, "Enter URL")
            input_el = wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='url']"))
            )
            input_el.clear()
            input_el.send_keys("https://en.wikipedia.org/wiki/Paris")
            click_text_button(driver, "Review claims first", timeout=60)
            wait_for_text(driver, "Edit the extracted claims before verification", timeout=240)
            save_screenshot(driver, "url-claim-review-desktop")
            summary["layout"]["urlClaimReviewDesktop"] = layout_state(driver)
            summary["checks"]["urlDraftClaimCount"] = len(
                driver.find_elements(By.XPATH, "//span[contains(normalize-space(.), 'Claim ')]")
            )
            summary["console_errors"].extend(browser_errors(driver))

        run_step(summary, "url_claim_review_desktop", url_review_flow)

        def mobile_pages() -> None:
            report_id = summary["checks"].get("reportId")
            if not report_id:
                raise AssertionError("No report id available for mobile report validation.")

            for name, path in [
                ("homeMobile", "/"),
                ("workspaceMobile", "/workspace"),
                ("reportMobile", f"/report/{report_id}"),
                ("historyMobile", "/history"),
            ]:
                driver.set_window_size(390, 844)
                goto(path)
                time.sleep(1.0)
                summary["layout"][name] = layout_state(driver)
                save_screenshot(driver, name.replace("Mobile", "-mobile").lower())
                summary["console_errors"].extend(browser_errors(driver))

            driver.set_window_size(1440, 1600)

        run_step(summary, "mobile_layouts", mobile_pages)

    finally:
        driver.quit()

    summary["console_errors"] = list(dict.fromkeys(summary["console_errors"]))
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
