import json
from datetime import datetime
from pathlib import Path  # TODO: remove it
from urllib.parse import parse_qs, urljoin, urlparse

import html2text
from bs4 import BeautifulSoup

from models import Post, Posts

text_maker = html2text.HTML2Text()
text_maker.ignore_links = True
text_maker.skip_internal_links = True
text_maker.ignore_images = True
text_maker.single_line_break = True

##################################################
# utils
##################################################


def is_string_contentent(string):
    for ch in string:
        if ch.isalpha() or ch.isdigit():
            return True
    return False


def filter_contentent_strings(iterable):
    return [string.strip() for string in iterable if is_string_contentent(string)]


def prettify_text(text):
    text = text.replace('#', '')
    text = text.replace('**', '*')
    lines = text.split('\n')
    lines = filter_contentent_strings(lines)
    return '\n'.join(lines)

##################################################
# parse short
##################################################


def parse_short_post(article_tag):
    # remove footer
    footer = article_tag.find('footer')
    footer.decompose()

    # post's metadata
    json_data = article_tag['data-ft']
    metadata = json.loads(json_data)

    html = str(article_tag)
    text = text_maker.handle(html)

    return Post(
        html=html,
        short_text=prettify_text(text),
        parse_timestamp=datetime.now().timestamp(),
        metadata=metadata
    )


def parse_feed_page(html):
    soup = BeautifulSoup(html, 'lxml')
    article_tags = soup.select('section>article')
    posts_gen = (parse_short_post(article_tag) for article_tag in article_tags)
    posts = [post for post in posts_gen if post]
    return posts


if __name__ == '__main__':
    html = Path('out.html').read_text(encoding='utf8')
    posts_list = parse_feed_page(html)

    posts = Posts()
    for post in posts_list:
        posts << post
        print(post)
        print()

    exit()
    json = posts.json()
    Path('result.json').write_text(json, encoding='utf8')

    pp = Posts.parse_file('result.json')
