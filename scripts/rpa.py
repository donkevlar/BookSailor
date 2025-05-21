from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import os
import logging

logger = logging.getLogger(__name__)


# TODO: switch to playwright or find to make async
class WebsiteNavigationRPA:
    def __init__(self, base_url, username=None, password=None, download_dir=None):
        """
        Initialize the RPA bot with configuration parameters

        Args:
            base_url (str): The website URL to navigate to
            username (str, optional): Login username
            password (str, optional): Login password
            download_dir (str, optional): Directory to save downloads
        """
        self.base_url = base_url
        self.username = username
        self.password = password
        self.files_downloaded = False
        self.magnet_link = None

        # Set up Chrome options
        chrome_options = Options()

        # Add options to handle common issues
        chrome_options.add_argument("--disable-notifications")  # Disable notifications
        chrome_options.add_argument("--disable-popup-blocking")  # Disable popup blocking
        chrome_options.add_argument('--headless=new')  # 'new' headless mode supports downloads
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

        # Optional: Add user agent to appear more like a regular browser
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Set download directory
        # Set download directory
        if download_dir:
            # Get absolute path
            if os.path.isabs(download_dir):
                self.download_dir = download_dir

            # Ensure directory exists
            if not os.path.exists(self.download_dir):
                os.makedirs(self.download_dir)

            # Convert to appropriate format for Chrome
            # Chrome needs forward slashes in the path, even on Windows
            chrome_download_dir = self.download_dir.replace('\\', '/')

            # Print for debugging
            logger.info(f"Setting download directory to: {chrome_download_dir}")

            prefs = {
                "download.default_directory": self.download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": False,
                "savefile.default_directory": chrome_download_dir,
                "profile.default_content_setting_values.automatic_downloads": 1
            }
            chrome_options.add_experimental_option("prefs", prefs)

        # Initialize WebDriver
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)  # 10 seconds timeout for wait conditions

    def quit_current_session(self):
        try:
            logger.info("Quitting session.")
            self.driver.quit()
        except Exception as e:
            logger.error(f'Error with quitting current session. {e}')

    def handle_login(self):
        """Handle login if required"""
        try:
            # Check if username input field exists
            username_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input.login-input[name="username"]'))
            )

            # If we're here, login is required
            logger.info("Login required. Attempting to login.")

            # Enter username
            username_field.clear()
            username_field.send_keys(self.username)

            # password
            password_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input.login-input[type="password"]'))
            )

            time.sleep(0.5)  # give the browser a moment after locating the field
            password_field.clear()
            password_field.send_keys(self.password)

            # Click login button
            login_button = self.driver.find_element(By.CSS_SELECTOR, '.login-button')
            login_button.click()

            try:
                # Verify if the user logged in.
                self.wait.until(
                    EC.url_to_be('https://audiobookbay.lu/member/users/')
                )
                logger.info("Login successful")
                return True

            except Exception as e:
                logger.error(f"Error logging into audiobook bay! {e}")
                return False

        except TimeoutException:
            # No login form found, continue with the process
            logger.info("No login required")
            pass

    def nav_login_page(self):
        url = "https://audiobookbay.lu/member/login.php"
        try:
            logger.info('Navigating to Login Page.')
            self.driver.get(url)

        except Exception as e:
            logger.error(f"Error navigating to login page! {e}")

    def get_search_result_titles(self, query):
        """Return a list of (title, url) tuples from search results without navigating."""

        logger.info(f"Searching for: {query}")

        try:
            # Try with search function filter
            # Find the search input and type a query
            search_input = self.driver.find_element(By.NAME, "s")
            search_input.clear()
            search_input.send_keys(query)

            # For AudioBookBay.lu, use direct URL format for search
            # Format: https://audiobookbay.lu/?s=your+search+terms
            search_url = f"{self.base_url}/?s={query.replace(' ', '+')}"
            logger.info(f"Using search URL: {search_url}")

            # Navigate directly to search URL
            timeout = 5  # seconds
            start = time.time()
            valid_page = False

            while time.time() - start < timeout:
                # Click on search button
                search_button = self.driver.find_element(By.CLASS_NAME, "searchSubmit")
                search_button.click()
                # self.driver.get(search_url)
                time.sleep(0.25)
                if self.driver.current_url == search_url or search_url in self.driver.current_url:
                    # Wait for search results to load
                    logger.info("Search complete")
                    valid_page = True
                    break

            if not valid_page:
                raise Exception('Search page could not be loaded!')

        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []

        try:
            posts = self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.post'))
            )
            logger.info(f"Found {len(posts)} posts")

            results = []
            for index, post in enumerate(posts):
                try:
                    title_element = post.find_element(By.CSS_SELECTOR, '.postTitle h2 a')
                    title = title_element.text
                    url = title_element.get_attribute("href")
                    logger.info(f"Found post {index + 1}: {title}")
                    results.append((title, url))
                except Exception as e:
                    logger.warning(f"Skipping post {index + 1} due to error: {e}")
                    continue

            return results

        except Exception as e:
            logger.error(f"Failed to retrieve post list: {e}")
            return []

    def process_post_by_url(self, title, url):
        """Given a title and URL, navigate and trigger download logic."""
        logger.info(f"Processing download for: {title}")
        self.driver.get(url)
        self.process_download_page()

    def process_download_page(self):
        self.files_downloaded = False
        """Process the download page to find and click download links on AudioBookBay.lu"""
        logger.info("Processing download page")

        try:
            magnet_button = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//*[contains(@id, 'magnetLink')]")
                )
            )

            magnet_button.click()

            magnet_icon = self.wait.until(
                EC.presence_of_element_located(
                    (By.ID, "magnetIcon")
                )
            )

            timeout = 5  # seconds
            start = time.time()
            magnet_url = None

            while time.time() - start < timeout:
                magnet_url = magnet_icon.get_attribute("href")
                if magnet_url:
                    break
                time.sleep(0.5)

            logger.info("Successfully retrieved magnet link, skipping download. ")
            logger.info(f"Tag Name: {magnet_icon.tag_name}, Magnet Link: {magnet_url}")
            self.magnet_link = magnet_url

            return magnet_url

        except Exception as e:
            logger.error(f"Could not get magnet link, attempting download. {e}")

        try:
            # Wait for the link to appear using text match
            torrent_button = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(text(), 'Torrent Free Downloads')]")
                )
            )

            relative_url = torrent_button.get_attribute("href")
            download_url = urljoin("https://audiobookbay.lu", relative_url)

            logger.info(f"Found torrent download URL: {download_url}")

            # Get list of files in download directory before starting download
            before_download = set(os.listdir(self.download_dir))

            # Click the torrent download link
            logger.info("Clicking torrent download button")
            torrent_button.click()
            # Confirm download started
            logger.info("Download initiated, waiting for file to appear...")

            # Wait and check for new files (download started)
            max_wait_time = 10  # seconds
            wait_interval = 1  # second
            download_started = False

            for _ in range(max_wait_time):
                time.sleep(wait_interval)
                current_files = set(os.listdir(self.download_dir))
                new_files = current_files - before_download

                # Look for temporary download files (Chrome uses .crdownload extension)
                temp_downloads = [f for f in new_files if f.endswith('.crdownload') or f.endswith('.part')]
                if temp_downloads:
                    download_started = True
                    logger.info(f"Download started: {temp_downloads}")
                    break

                # Or if the download is very fast and already completed
                if new_files and not any(f.endswith('.crdownload') or f.endswith('.part') for f in new_files):
                    download_started = True
                    files_ = []
                    logger.info(f"Download instantly completed: {new_files}")
                    self.files_downloaded = True
                    files_.append(new_files)
                    return files_  # Return the downloaded files

            if not download_started:
                logger.warning("No download appears to have started after waiting")
                return []

            # Wait for download to complete (temp files to disappear)
            logger.info("Waiting for download to complete...")
            download_complete = False

            for _ in range(max_wait_time * 2):  # Longer wait for completion
                time.sleep(wait_interval)
                current_files = set(os.listdir(self.download_dir))

                # Check if any temp download files still exist
                if not any(f.endswith('.crdownload') or f.endswith('.part') for f in current_files):
                    download_complete = True
                    new_files = current_files - before_download
                    logger.info(f"Download completed: {new_files}")
                    return list(new_files)  # Return the downloaded files

            if not download_complete:
                logger.warning("Download may still be in progress after maximum wait time")
                return []

        except Exception as e:
            logger.error(f"Error on download page: {e}")
            raise


if __name__ == "__main__":
    print("Where's RACHEL!!!!!")
