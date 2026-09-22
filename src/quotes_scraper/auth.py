"""Login through the real login form and verify it worked."""

import logging

from quotes_scraper.scraper import BASE_URL, TIMEOUT_MS, ScraperError, goto_with_retry

log = logging.getLogger(__name__)

LOGIN_URL = BASE_URL + "/login"


def login(page, username, password):
    """Log in via the form. Raises ScraperError if login cannot be verified.

    We drive the real form (rather than POSTing) because it carries a hidden
    CSRF token that the browser submits for us. The site accepts any
    credentials, so success is verified by the presence of a "Logout" link.
    The password is never logged.
    """
    log.info("Logging in as %s", username)
    goto_with_retry(page, LOGIN_URL)
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("input[type=submit]")
    try:
        page.wait_for_selector("a:text-is('Logout')", timeout=TIMEOUT_MS)
    except Exception as exc:  # Playwright timeout: no Logout link appeared
        raise ScraperError(
            "Login failed: no 'Logout' link found after submitting the login form."
        ) from exc
