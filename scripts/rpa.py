from urllib.parse import urlencode, urljoin

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class _BrowserlessDriverShim:
    def __init__(self, rpa: "WebsiteNavigationRPA"):
        self._rpa = rpa

    def get(self, url: str):
        self._rpa.current_url = url

    def close(self):
        self._rpa.current_url = None

    def quit(self):
        self.close()


class WebsiteNavigationRPA:
    def __init__(self, base_url, username=None, password=None, download_dir=None):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.title = None
        self.author = None
        self.files_downloaded = False
        self.magnet_link = None
        self.current_url = None
        self.download_dir = os.path.abspath(download_dir) if download_dir else None
        self.browserless_token = os.getenv("BROWSERLESS_TOKEN")
        self.browserless_base_url = (
            os.getenv("BROWSERLESS_URL")
            or os.getenv("BROWSERLESS_BASE_URL")
            or "http://localhost:3000"
        ).rstrip("/")
        self.driver = _BrowserlessDriverShim(self)

        if self.download_dir:
            os.makedirs(self.download_dir, exist_ok=True)

    def _function_urls(self) -> list[str]:
        explicit = os.getenv("BROWSERLESS_FUNCTION_URL")
        if explicit:
            return [explicit]

        paths = ("/function", "/chrome/function", "/chromium/function")
        urls = []
        for path in paths:
            url = f"{self.browserless_base_url}{path}"
            if self.browserless_token:
                url = f"{url}?{urlencode({'token': self.browserless_token})}"
            urls.append(url)
        return urls

    def _execute_browserless(self, script: str) -> Any:
        errors = []
        headers = {
            "Content-Type": "application/javascript",
            "Cache-Control": "no-cache",
        }

        for url in self._function_urls():
            for payload_mode in ("raw", "json"):
                try:
                    if payload_mode == "raw":
                        response = requests.post(url, data=script, headers=headers, timeout=90)
                    else:
                        response = requests.post(url, json={"code": script}, timeout=90)

                    response.raise_for_status()

                    if not response.text.strip():
                        return {}

                    try:
                        return response.json()
                    except ValueError:
                        return {"value": response.text}

                except requests.RequestException as exc:
                    errors.append(f"{payload_mode} {url}: {exc}")

        raise RuntimeError("Browserless request failed: " + " | ".join(errors))

    def _build_script(self, action: str, **kwargs) -> str:
        payload = {
            "action": action,
            "base_url": self.base_url,
            "login_url": f"{self.base_url}/member/login.php",
            "username": self.username,
            "password": self.password,
            "user_agent": DEFAULT_USER_AGENT,
            **kwargs,
        }
        payload_json = json.dumps(payload)
        return f"""
module.exports = async ({{ page }}) => {{
  const payload = {payload_json};

  const maybeLogin = async () => {{
    if (!payload.username || !payload.password) {{
      return false;
    }}

    await page.goto(payload.login_url, {{ waitUntil: 'domcontentloaded' }});
    const usernameField = await page.$('input.login-input[name="username"]');
    if (!usernameField) {{
      return false;
    }}

    await page.type('input.login-input[name="username"]', payload.username, {{ delay: 30 }});
    await page.type('input.login-input[type="password"]', payload.password, {{ delay: 30 }});
    await Promise.all([
      page.click('.login-button'),
      page.waitForNavigation({{ waitUntil: 'domcontentloaded', timeout: 10000 }}).catch(() => null),
    ]);

    return page.url().includes('/member/users/');
  }};

  await page.setUserAgent(payload.user_agent);
  await page.setViewport({{ width: 1440, height: 1024 }});

  switch (payload.action) {{
    case 'login': {{
      const loggedIn = await maybeLogin();
      return {{ logged_in: loggedIn, current_url: page.url() }};
    }}

    case 'search': {{
      await maybeLogin();
      const searchUrl = `${{payload.base_url}}/?s=${{encodeURIComponent(payload.query)}}`;
      await page.goto(searchUrl, {{ waitUntil: 'domcontentloaded' }});
      await page.waitForSelector('div.post', {{ timeout: 10000 }}).catch(() => null);
      const results = await page.$$eval('div.post', (posts) =>
        posts.map((post) => {{
          const link = post.querySelector('.postTitle h2 a');
          return link ? {{ title: link.textContent.trim(), url: link.href }} : null;
        }}).filter(Boolean)
      );
      return {{ results, current_url: page.url() }};
    }}

    case 'post_info': {{
      await maybeLogin();
      await page.goto(payload.url, {{ waitUntil: 'domcontentloaded' }});
      await page.waitForSelector('h1[itemprop="name"]', {{ timeout: 10000 }});
      const info = await page.evaluate(() => {{
        const title = document.querySelector('h1[itemprop="name"]')?.textContent?.trim() ?? null;
        const author = document.querySelector('span.author')?.textContent?.trim() ?? null;
        return {{ title, author }};
      }});
      return {{ ...info, current_url: page.url() }};
    }}

    case 'download': {{
      await maybeLogin();
      await page.goto(payload.url, {{ waitUntil: 'domcontentloaded' }});

      let magnetLink = null;
      const magnetButton = await page.$('[id*="magnetLink"]');
      if (magnetButton) {{
        await magnetButton.click();
        await page.waitForSelector('#magnetIcon', {{ timeout: 5000 }}).catch(() => null);
        magnetLink = await page.$eval('#magnetIcon', (el) => el.getAttribute('href')).catch(() => null);
      }}

      let torrentUrl = null;
      if (!magnetLink) {{
        const torrentButton = await page.$x("//a[contains(text(), 'Torrent Free Downloads')]");
        if (torrentButton.length) {{
          torrentUrl = await page.evaluate((el) => el.getAttribute('href'), torrentButton[0]);
        }}
      }}

      return {{
        magnet_link: magnetLink,
        torrent_url: torrentUrl,
        current_url: page.url(),
      }};
    }}

    default:
      throw new Error(`Unsupported action: ${{payload.action}}`);
  }}
}};
""".strip()

    def quit_current_session(self):
        try:
            logger.info("Quitting browserless session.")
            self.driver.quit()
        except Exception as e:
            logger.error(f"Error with quitting current session. {e}")

    def handle_login(self):
        try:
            result = self._execute_browserless(self._build_script("login"))
            logged_in = bool(result.get("logged_in"))
            self.current_url = result.get("current_url")
            if logged_in:
                logger.info("Login successful")
            else:
                logger.info("No login required or login could not be verified")
            return logged_in
        except Exception as e:
            logger.error(f"Error logging into audiobook bay! {e}")
            return False

    def nav_login_page(self):
        self.current_url = f"{self.base_url}/member/login.php"
        logger.info("Prepared login page navigation for Browserless.")

    def get_search_result_titles(self, query):
        logger.info(f"Searching for: {query}")

        try:
            result = self._execute_browserless(self._build_script("search", query=query))
            self.current_url = result.get("current_url")
            results = result.get("results", [])
            logger.info(f"Found {len(results)} posts")
            return [(item["title"], item["url"]) for item in results if item.get("title") and item.get("url")]
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []

    def get_post_info(self):
        if not self.current_url:
            logger.error("No current URL set before requesting post info.")
            return None

        try:
            result = self._execute_browserless(self._build_script("post_info", url=self.current_url))
            self.current_url = result.get("current_url")
            self.title = result.get("title")
            self.author = result.get("author")
            return self.title, self.author
        except Exception as e:
            logger.error(f"Could not find title or author due to an error... {e}")
            return None

    def process_post_by_url(self, title, url):
        logger.info(f"Processing download for: {title}")
        self.current_url = url
        return self.process_download_page()

    def process_download_page(self):
        self.files_downloaded = False
        self.magnet_link = None

        if not self.current_url:
            raise ValueError("No current URL set for download processing.")

        logger.info("Processing download page")

        try:
            result = self._execute_browserless(self._build_script("download", url=self.current_url))
            self.current_url = result.get("current_url")
            self.magnet_link = result.get("magnet_link")

            if self.magnet_link:
                logger.info(f"Successfully retrieved magnet link: {self.magnet_link}")
                return self.magnet_link

            torrent_url = result.get("torrent_url")
            if torrent_url:
                if not torrent_url.startswith("http"):
                    torrent_url = urljoin(self.base_url, torrent_url)
                logger.info(f"Found torrent download URL: {torrent_url}")
                return torrent_url

            logger.error("No magnet link or torrent URL found on download page.")
            return None

        except Exception as e:
            logger.error(f"Error on download page: {e}")
            raise


if __name__ == "__main__":
    print("Where's RACHEL!!!!!")
