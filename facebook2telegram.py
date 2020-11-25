'''
TODO:
1. loguru - also to file
2. ...
'''

from selenium.webdriver import Chrome, ChromeOptions
from selenium.common.exceptions import NoSuchElementException
from decouple import config
import telebot
from loguru import logger
from slugify import slugify

from time import sleep
from urllib.parse import urljoin
from pathlib import Path
import json
from datetime import datetime, timedelta

from fbparser import parse_feed_page
from models import Settings, Posts

BASE_URL = 'https://d.facebook.com/'
FB_MAIN_URL = BASE_URL
FB_LOGIN_URL = BASE_URL
FB_MOST_RECENT_URL = urljoin(BASE_URL, 'home.php?sk=h_chr')

DEFAULT_MAX_POSTS = 200
FIRST_TIME_POSTS_COUNT = 10

APP_DIR = Path(__file__).parent

class FBConnector():
	def __init__(self, fb_login, fb_password):
		self.fb_login = fb_login
		self.fb_password = fb_password
		self.driver = None
		
	def start_webdriver(self):
		if self.driver is None:
			options = ChromeOptions()
			#TODO:remove options.headless = True 
			options.add_experimental_option("excludeSwitches", ["enable-logging"])
			self.driver = Chrome(options=options)
			logger.info('Webdriver started')
			self.login()

	def login(self):
		logger.info('Logging in to Facebook')
		self.driver.get(FB_LOGIN_URL)
		logger.info('Login page opened')
		sleep(3)
		
		username = self.driver.find_element_by_id('m_login_email')
		username.send_keys(self.fb_login)
		password = self.driver.find_element_by_name('pass')
		password.send_keys(self.fb_password)
		logger.info('Credentials entered')
		
		submit   = self.driver.find_element_by_name('login')
		submit.click()
		logger.info('Credentials submitted')
		sleep(2)
		
	def quit_webdriver(self):
		if self.driver is not None:
			self.driver.quit()		
			self.driver = None
			logger.info('Webdriver quited')
		
	def __del__(self):
		self.quit_webdriver()
		
	def iter_posts(self, feed_url=FB_MOST_RECENT_URL, max_posts=None):
		posts_count = max_posts or DEFAULT_MAX_POSTS
		logger.info('Getting recent post webpage')
		
		self.start_webdriver()
		self.driver.get(feed_url)
		while True:
			html = self.driver.page_source
			posts = parse_feed_page(html)
			for post in posts:
				yield post
				posts_count -= 1
				if not posts_count:
					return # stop iteration
			logger.info('Getting next page of feed')
			try:
				next_page_link = self.driver.find_element_by_css_selector('#objects_container section+a')
			except NoSuchElementException:
				logger.info('No link to next page')
				return # stop iteration
			next_page_link.click()
		
class FB2Telegram:
	def __init__(self, fb_login, fb_password, tg_token, tg_chat_id):
		self.fb_login = fb_login
		self.fb_password = fb_password
		self.tg_token = tg_token
		self.tg_chat_id = tg_chat_id
		self.fb = FBConnector(self.fb_login, self.fb_password)
		self.load_settings()
		
	def get_settings_file_name(self):
		return f"{slugify(self.fb_login)}.json"
		
	def get_settings_file(self):
		return APP_DIR / self.get_settings_file_name()
		
	def save_settings(self):
		self.get_settings_file().write_text(self.settiings.json(indent=2))
			
	def load_settings(self):
		settings_file = self.get_settings_file()
		if settings_file.exists():
			self.settiings = Settings.parse_file(settings_file)
		else:
			self.settiings = Settings()
			self.save_settings()
		
	def get_new_posts(self, max_posts=None):
		new_posts = Posts()
		for post in self.fb.iter_posts(max_posts=max_posts):
			if post in self.settiings.posts:
				logger.info('No more new posts')
				break
			self.settiings.posts << post
			new_posts << post
			log_text = post.short_text.split('\n')[0]
			logger.info(f">> {log_text}...")
		self.settiings.last_update_datetime = datetime.now()
		self.save_settings()
		logger.info(f"{len(new_posts)} new posts parsed")
		return new_posts
		
	def can_update(self):
		return datetime.now() - self.settiings.last_update_datetime >= \
			timedelta(seconds=60*self.settiings.wait_before_next_update)
		
	def update(self):
		if not self.can_update():
			logger.warning(f"Last update was less then {self.settiings.wait_before_next_update} minutes ago. Update aborted")
			return
		if self.settiings.posts:
			logger.info('Updating...')
			new_posts = self.get_new_posts()
		else:
			logger.info(f"This is first time update. Getting recent {FIRST_TIME_POSTS_COUNT} posts")
			new_posts = self.get_new_posts(max_posts=FIRST_TIME_POSTS_COUNT)
		if new_posts:
			self.send_posts_to_telegram(new_posts)
		return new_posts
				
	def send_posts_to_telegram(self, posts):
		logger.info(f"Sending {len(posts)} posts to Telegram...")
		bot = telebot.TeleBot(self.tg_token)
		for post in reversed(posts):
			post_url = urljoin(BASE_URL, post.id)
			text = f"{post.short_text}\n[{self.settiings.link_text}]({post_url})"
			try:
				bot.send_message(
					chat_id=self.tg_chat_id,
					text=text,
					disable_web_page_preview=True,
					# disable_notification=True,
					parse_mode='markdown'
				)
			except Exception as e:
				logger.error(f"Can't send... {e}")
				loguru.error(text)
				continue

def get_app():
	app = FB2Telegram(
		fb_login = config('FB2TG_FB_LOGIN'),
		fb_password = config('FB2TG_FB_PASSWORD'),
		tg_token = config('FB2TG_TG_TOKEN'),
		tg_chat_id = config('FB2TG_TG_CHAT_ID')
	)
	return app

