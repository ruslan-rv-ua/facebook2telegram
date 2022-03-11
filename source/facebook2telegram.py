import string
import atexit
import json
import sys
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from time import sleep
from types import new_class
from urllib.parse import urljoin

import html2text
import telebot
from bs4 import BeautifulSoup
from loguru import logger
from mongita import MongitaClientDisk
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import Chrome, ChromeOptions


BASE_URL = "https://d.facebook.com/"
FB_MAIN_URL = BASE_URL
FB_LOGIN_URL = BASE_URL
FB_MOST_RECENT_URL = urljoin(BASE_URL, "home.php?sk=h_chr")

DEFAULT_MAX_POSTS = 200
FIRST_TIME_POSTS_COUNT = 10

APP_DIR = Path(__file__).parent
BROWSER_DIR_NAME = "Chrome-bin"


text_maker = html2text.HTML2Text()
text_maker.ignore_links = True
text_maker.skip_internal_links = True
text_maker.ignore_images = True
text_maker.single_line_break = True


@dataclass
class Post:
    html: str
    metadata: dict
    _id: int = None
    post_id: str = ""
    sent_to_telegram: bool = False

    def __post_init__(self):
        self.post_id = self.metadata.get("top_level_post_id")

    @property
    def short_text(self) -> str:
        def is_char_acceptable(char: str) -> bool:
            return char.isalnum() or char.isspace() or char in string.punctuation
        def is_line_acceptable(line:str) -> bool:
            return any(ch.isalnum() for ch in line)

        text = text_maker.handle(self.html)  # html to markdown
        text = (
            text.replace("#", "").replace("*", "").replace("_", "")
        )  # remove markdown symbols
        text = "".join(filter(is_char_acceptable, text))  # filter unwanted chars
        lines = [
            stripped_line
            for line in text.split("\n")
            if is_line_acceptable(stripped_line := line.strip())
        ]
        return "\n".join(lines)

    @classmethod
    def parse_article_tag(cls, article_tag):
        # remove footer
        footer = article_tag.find("footer")
        footer.decompose()

        # post's metadata
        metadata = json.loads(article_tag["data-ft"])
		# https://docs.google.com/spreadsheets/d/11dfj6LJks7C7mLi4eSrrW28K1KabgGiPaYb9Fh5Tj3U/edit#gid=0

        return cls(
            html=str(article_tag),
            metadata=metadata,
        )


class FBConnector:
    def __init__(self, fb_login, fb_password):
        self.fb_login = fb_login
        self.fb_password = fb_password
        self.driver = None
        atexit.register(self.quit_webdriver)

    def start_webdriver(self):
        if self.driver is None:
            options = ChromeOptions()
            # TODO:remove options.headless = True
            options.binary_location = str(APP_DIR / BROWSER_DIR_NAME / "chrome.exe")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            # self.driver = Chrome(APP_DIR / BROWSER_DIR / 'chrome.exe', options=options)
            self.driver = Chrome(APP_DIR / "chromedriver.exe", options=options)
            logger.info("Webdriver started")

    def login(self):
        logger.info(f"Logging in to Facebook as {self.fb_login}")
        self.driver.get(FB_LOGIN_URL)
        logger.info("Login page opened")
        sleep(3)

        username = self.driver.find_element_by_id("m_login_email")
        username.send_keys(self.fb_login)
        password = self.driver.find_element_by_name("pass")
        password.send_keys(self.fb_password)
        logger.info("Credentials entered")

        submit = self.driver.find_element_by_name("login")
        submit.click()
        logger.info("Credentials submitted")
        sleep(2)

    def quit_webdriver(self):
        if self.driver is not None:
            self.driver.quit()
            self.driver = None
            logger.info("Webdriver quited")

    def __enter__(self):
        self.start_webdriver()
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit_webdriver()

    @staticmethod
    def parse_feed_page(html):
        soup = BeautifulSoup(html, "lxml")
        article_tags = soup.select("section>article")
        posts = [Post.parse_article_tag(article_tag) for article_tag in article_tags]
        return posts

    def iter_posts(self, feed_url=FB_MOST_RECENT_URL, max_posts=None):
        posts_count = max_posts or DEFAULT_MAX_POSTS
        logger.info("Getting feed webpage")

        self.start_webdriver()
        self.driver.get(feed_url)
        while True:
            html = self.driver.page_source
            posts = self.parse_feed_page(html)
            for post in posts:
                yield post
                posts_count -= 1
                if not posts_count:
                    return  # stop iteration
            logger.info("Getting next page of feed")
            try:
                next_page_link = self.driver.find_element_by_css_selector(
                    "#objects_container section+a"
                )
            except NoSuchElementException:
                logger.info("No link to next page")
                return  # stop iteration
            next_page_link.click()


class Facebook2Telegram:
    def __init__(self, fb_login, fb_password, tg_token, tg_chat_id):
        self.fb_login = fb_login
        self.fb_password = fb_password
        self.tg_token = tg_token
        self.tg_chat_id = tg_chat_id
        db_client = MongitaClientDisk(host=APP_DIR / "db")
        db = db_client.facebook2telegram
        self.posts_collection = db.posts

    def get_new_posts(self, max_posts=None):
        with FBConnector(self.fb_login, self.fb_password) as fb_connector:
            for post in fb_connector.iter_posts(max_posts=max_posts):
                if self.posts_collection.count_documents({"post_id": post.post_id}) > 0:
                    logger.info("No more new posts")
                    break
                self.posts_collection.insert_one(asdict(post))
                log_text = post.short_text.split("\n")[0]
                logger.info(f">> {log_text}...")

    def update(self):
        if self.posts_collection.count_documents({}) > 0:
            logger.info("Updating...")
            self.get_new_posts()
        else:
            logger.info(
                f"This is first time update. Getting recent {FIRST_TIME_POSTS_COUNT} posts"
            )
            self.get_new_posts(max_posts=FIRST_TIME_POSTS_COUNT)
        self.send_posts_to_telegram()

    def send_posts_to_telegram(self):
        unsent_posts_count = self.posts_collection.count_documents(
            {"sent_to_telegram": False}
        )
        if unsent_posts_count == 0:
            return
        logger.info(f"Sending {unsent_posts_count} posts to Telegram...")
        bot = telebot.TeleBot(self.tg_token)
        for post_record in self.posts_collection.find({"sent_to_telegram": False}):
            post = Post(**post_record)
            post_url = urljoin(BASE_URL, post.post_id)
            text = f"{post.short_text}\n[link]({post_url})"
            try:
                bot.send_message(
                    chat_id=self.tg_chat_id,
                    text=text,
                    disable_web_page_preview=True,
                    # disable_notification=True,
                    parse_mode="markdown",
                )
            except Exception as e:
                logger.exception(f"Can't send...\n{text}")
                continue
            self.posts_collection.update_one(
                {"_id": post_record["_id"]}, update={"$set": {"sent_to_telegram": True}}
            )


logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    # format="<green>{time:YYYY-MM-DD at HH:mm:ss}</green> <level>{message}</level>")
    format="<level>{level:10}| {message}</level>",
)
logger.add("facebook2telegram.log", encoding="utf8", rotation="3 days")
