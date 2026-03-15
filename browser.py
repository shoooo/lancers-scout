"""
Playwright-based browser session for Lancers.
Handles login, session persistence, and authenticated page fetching.
"""

import os
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page

SESSION_FILE = Path(__file__).parent / ".session.json"
BASE_URL = "https://www.lancers.jp"
LOGIN_URL = f"{BASE_URL}/user/login"


def _load_env_credentials() -> tuple[str, str]:
    email = os.environ.get("LANCERS_EMAIL", "")
    password = os.environ.get("LANCERS_PASSWORD", "")
    if not email or not password:
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("LANCERS_EMAIL="):
                    email = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("LANCERS_PASSWORD="):
                    password = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not email or not password:
        raise ValueError(
            "Lancers credentials not found.\n"
            "Add to your .env file:\n"
            "  LANCERS_EMAIL=your@email.com\n"
            "  LANCERS_PASSWORD=yourpassword"
        )
    return email, password


class LancersSession:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self.context: BrowserContext = None
        self.page: Page = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self.context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        # Restore saved session if available
        if SESSION_FILE.exists():
            try:
                cookies = json.loads(SESSION_FILE.read_text())
                self.context.add_cookies(cookies)
                print("  Restored saved session.")
            except Exception:
                pass

        self.page = self.context.new_page()
        return self

    def __exit__(self, *args):
        # Save session cookies before closing
        try:
            cookies = self.context.cookies()
            SESSION_FILE.write_text(json.dumps(cookies))
        except Exception:
            pass
        self._browser.close()
        self._playwright.stop()

    def is_logged_in(self) -> bool:
        self.page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=15000)
        return "/dashboard" in self.page.url and "login" not in self.page.url

    def login(self) -> bool:
        email, password = _load_env_credentials()
        print("  Logging in to Lancers...")

        self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=15000)
        self.page.fill('input[name="data[User][email]"], input[type="email"]', email)
        self.page.fill('input[name="data[User][password]"], input[type="password"]', password)
        self.page.click('button[type="submit"], input[type="submit"]')
        self.page.wait_for_load_state("domcontentloaded", timeout=15000)

        if "login" in self.page.url:
            raise RuntimeError("Login failed — check your LANCERS_EMAIL and LANCERS_PASSWORD in .env")

        # Handle 2FA / email verification code
        if "verify_code" in self.page.url:
            if self.headless:
                raise RuntimeError(
                    "Lancers is asking for an email verification code.\n"
                    "Run once with --headful to complete 2FA manually:\n"
                    "  python3 browser.py --setup\n"
                    "After that, the session will be saved and used automatically."
                )
            print("  Email verification required — check your email and enter the code in the browser.")
            # Wait up to 3 minutes for the user to complete verification
            self.page.wait_for_url(f"{BASE_URL}/dashboard", timeout=180000)
            print("  Verification complete.")

        print("  Logged in successfully.")
        return True

    def ensure_logged_in(self):
        """Check session validity, login if needed."""
        if not self.is_logged_in():
            self.login()

    def update_profile(self, profile: dict) -> bool:
        """
        Update Lancers profile (bio, tagline, hourly rate) from profile dict.
        Returns True on success.
        """
        self.ensure_logged_in()
        PROFILE_URL = f"{BASE_URL}/mypage/profile"

        print(f"  Opening profile edit page...")
        self.page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=20000)

        # 一言PR / subtitle tagline
        subtitle = profile.get("strengths", "")
        sub_el = self.page.query_selector('input[name="data[UserProfile][sub_title]"]')
        if sub_el:
            sub_el.fill(subtitle[:100])  # Lancers caps at ~100 chars
            print("  Filled 一言PR (subtitle).")

        # 自己PR / description
        note = profile.get("note", "")
        desc_el = self.page.query_selector('textarea[name="data[UserProfile][description]"]')
        if desc_el:
            desc_el.fill(note)
            print("  Filled 自己PR (description).")

        # Hourly rate
        rate = profile.get("hourly_rate")
        if rate:
            rate_el = self.page.query_selector('input[name="data[UserProfile][timecharge_rate]"]')
            if rate_el:
                rate_el.fill(str(rate))
                print(f"  Filled hourly rate: ¥{rate}")

        # Save
        save_btn = self.page.query_selector('button[type="submit"]:has-text("保存")')
        if not save_btn:
            save_btn = self.page.query_selector('button[type="submit"], input[type="submit"]')

        if save_btn:
            save_btn.click()
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            print("  Profile saved.")
        else:
            print("  Could not find save button.")
            return False

        # --- Update Skills tab ---
        print("  Navigating to skills tab...")
        self.page.goto(f"{BASE_URL}/skill", wait_until="domcontentloaded", timeout=20000)
        self.page.screenshot(path="/tmp/skills_page.png")
        print("  Skills page screenshot saved to /tmp/skills_page.png")
        print("  Note: Skill tags require individual search + click on Lancers.")
        print("  Please add skills manually from lancers_profile_text.md")

        return True

    def get_html(self, url: str) -> str:
        """Navigate to URL and return page HTML."""
        self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return self.page.content()

    def submit_proposal(self, project_url: str, proposal_text: str, budget: str = None, confirm: bool = True) -> bool:
        """
        Navigate to a project and submit a proposal.
        If confirm=True, prints the proposal and asks for user confirmation first.
        Returns True if submitted successfully.
        """
        self.ensure_logged_in()

        # Go to the project detail page
        self.page.goto(project_url, wait_until="domcontentloaded", timeout=15000)

        # Click 「提案する」 button
        propose_btn = self.page.query_selector(
            'a:has-text("提案する"), button:has-text("提案する"), a[href*="propose"]'
        )
        if not propose_btn:
            print(f"  [skip] No '提案する' button found on {project_url}")
            return False

        if confirm:
            print(f"\n  Proposal to submit:")
            print(f"  URL: {project_url}")
            print(f"  {'─'*50}")
            for line in proposal_text.splitlines():
                print(f"  {line}")
            print(f"  {'─'*50}")
            answer = input("  Submit this proposal? [y/N] ").strip().lower()
            if answer != "y":
                print("  Skipped.")
                return False

        propose_btn.click()
        self.page.wait_for_load_state("domcontentloaded", timeout=10000)

        # Fill proposal text
        textarea = self.page.query_selector(
            'textarea[name*="body"], textarea[name*="message"], textarea[name*="proposal"], textarea'
        )
        if not textarea:
            print(f"  [error] Could not find proposal textarea on {self.page.url}")
            return False

        textarea.fill(proposal_text)

        # Fill budget if provided and field exists
        if budget:
            budget_field = self.page.query_selector(
                'input[name*="budget"], input[name*="price"], input[name*="amount"]'
            )
            if budget_field:
                clean_budget = "".join(c for c in budget if c.isdigit())
                if clean_budget:
                    budget_field.fill(clean_budget)

        # Submit
        submit_btn = self.page.query_selector(
            'button[type="submit"]:has-text("提案"), input[type="submit"], button:has-text("送信")'
        )
        if not submit_btn:
            print("  [error] Could not find submit button.")
            return False

        submit_btn.click()
        self.page.wait_for_load_state("domcontentloaded", timeout=10000)

        # Check success
        success = self.page.query_selector('[class*="success"], [class*="complete"], :has-text("提案しました")')
        if success or "complete" in self.page.url or "success" in self.page.url:
            print(f"  Proposal submitted!")
            return True
        else:
            print(f"  Warning: submission may not have completed. Check {self.page.url}")
            return False
