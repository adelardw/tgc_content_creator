import requests
from bs4 import BeautifulSoup
from loguru import logger
import random
# import sys #DEBUG
# import os #DEBUG
#sys.path.append(os.path.abspath(os.path.curdir)) #DEBUG
from src.tools.config import user_agents, save_yaml



def parse_count(count_str: str) -> int:
    """
    Преобразует строку с количеством (например, '1.2K', '5M') в целое число.
    """
    if not count_str:
        return 0
    count_str = count_str.strip().upper()
    multiplier = 1
    if 'K' in count_str:
        multiplier = 1000
        count_str = count_str.replace('K', '')
    elif 'M' in count_str:
        multiplier = 1000000
        count_str = count_str.replace('M', '')
    try:
        return int(float(count_str) * multiplier)
    except (ValueError, TypeError):
        return 0


def get_all_tgstat_channel_themes() -> list[str]:
    '''
    Находит разделы с https://tgstat.ru/
    '''
    res = requests.get('https://tgstat.ru/',
                       headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win86; x86) AppleWebKit/537.36'})
    bs = BeautifulSoup(res.content, 'html.parser')
    themes = bs.find_all('a', class_='text-dark')
    th_res = set()

    for t in themes:
        her = t.get('href')
        if her.startswith('/') and len(her.split('/')) - 1 == 1:
            th_res.add(her[1:])

    save_yaml(list(th_res),'tgstat_endpoints')
    return th_res


def find_channel_names(tgstat_channel_theme: str,
                       headers: dict = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.5',
                                'Accept-Encoding': 'gzip, deflate',
                                'DNT': '1', # Do Not Track
                                'Connection': 'keep-alive',
                                'Upgrade-Insecure-Requests': '1',
                                'Sec-Fetch-Dest': 'document',
                                'Sec-Fetch-Mode': 'navigate',
                                'Sec-Fetch-Site': 'none',
                                'Sec-Fetch-User': '?1'}) -> list[str]:
    """
    Парсит tgstat, находя нужные каналы с тематикой tgstat_channel_theme
    """
    base_url = f'https://tgstat.ru/{tgstat_channel_theme}'
    headers['User-Agent'] = random.choice(user_agents)
    resp = requests.get(base_url,
                        headers=headers)
    bs = BeautifulSoup(resp.content, 'html.parser')
    hrefs = bs.find_all('a', class_="text-body")
    tgc_names = []
    for her in hrefs:
        linnk = her.get('href')
        pos = linnk.find('@')
        if pos > 0:
            tgc_names.append(linnk[pos + 1:])

    return tgc_names

def get_channel_posts(channel_name: str, k: int = 5,
                      headers: dict = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.5',
                                'Accept-Encoding': 'gzip, deflate',
                                'DNT': '1',
                                'Connection': 'keep-alive',
                                'Upgrade-Insecure-Requests': '1',
                                'Sec-Fetch-Dest': 'document',
                                'Sec-Fetch-Mode': 'navigate',
                                'Sec-Fetch-Site': 'none',
                                'Sec-Fetch-User': '?1'}):
    """
    Парсит последние k постов из публичного Telegram-канала, включая реакции.
    (Версия, исправленная на основе предоставленного пользователем HTML)
    """
    headers['User-Agent'] = random.choice(user_agents)
    base_url = f"https://t.me/s/{channel_name}"
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к {base_url}: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    messages = soup.find_all('div', class_='tgme_widget_message_wrap')

    if not messages:
        logger.debug(f"Не удалось найти посты в канале '{channel_name}'."
                     "Возможно, делается несколько пересылок и сейчас обрабатываются "\
                     "медиа группы.")
        return []

    parsed_posts = []

    for message_widget in reversed(messages[-k:]):
        post_data = {}

        datetime = message_widget.find('a', class_='tgme_widget_message_date').\
                                find('time', class_='time')['datetime']
                                
        text_element = message_widget.find('div', class_='tgme_widget_message_text')
        text = text_element.get_text(separator='\n', strip=True) if text_element else ""
        post_data['text'] = text
        post_data['datetime'] = datetime

        is_ads = False
        for a_tag in text_element.find_all('a'):
            if a_tag.has_attr('href'):
                link_url = a_tag['href']
                if 'erid' in link_url.lower():
                    is_ads = True
                    break

        post_data['is_ads'] = is_ads
        media_links = []
        views_element = message_widget.find('span', class_='tgme_widget_message_views')
        views_element = parse_count(views_element.text)
        post_data['num_post_views'] = views_element
        media_elements = message_widget.find_all('a', class_='tgme_widget_message_photo_wrap') or \
                        message_widget.find_all('i', class_='tgme_widget_message_video_thumb')

        for media in media_elements:
            style = media.get('style', '')
            if 'background-image:url(' in style:
                link = style.split("url('")[1].split("')")[0]
                media_links.append(link)
        post_data['media_links'] = media_links

        post_link_element = message_widget.find('a', class_='tgme_widget_message_date')
        post_data['post_url'] = post_link_element['href'] if post_link_element else 'N/A'


        reactions_data = {}
        reactions_container = message_widget.find('div', class_='tgme_widget_message_reactions')
        if reactions_container:

            reaction_elements = reactions_container.find_all('span', class_='tgme_reaction')

            for reaction in reaction_elements:
                emoji_char = ''
                count_str = ''

                emoji_el = reaction.find('b')
                if emoji_el:
                    emoji_char = emoji_el.text.strip()

                full_text = reaction.text.strip()
                if emoji_char:
                    count_str = full_text.replace(emoji_char, '').strip()
                else:
                    count_str = ''.join(filter(str.isdigit, full_text))

                if emoji_char and count_str:
                    reactions_data[emoji_char] = parse_count(count_str)

        post_data['reactions'] = reactions_data
        parsed_posts.append(post_data)

    return parsed_posts


def get_channel_single_post_info(channel_name: str, post_id: str,
                      headers: dict = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.5',
                                'Accept-Encoding': 'gzip, deflate',
                                'DNT': '1',
                                'Connection': 'keep-alive',
                                'Upgrade-Insecure-Requests': '1',
                                'Sec-Fetch-Dest': 'document',
                                'Sec-Fetch-Mode': 'navigate',
                                'Sec-Fetch-Site': 'none',
                                'Sec-Fetch-User': '?1'}):
    """
    Парсит последние k постов из публичного Telegram-канала, включая реакции.
    (Версия, исправленная на основе предоставленного пользователем HTML)
    """
    headers['User-Agent'] = random.choice(user_agents)
    base_url = f"https://t.me/s/{channel_name}/{post_id}"
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к {base_url}: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    post_selector = f'div[data-post="{channel_name}/{post_id}"]'
    message_container = soup.select_one(post_selector)


    if not message_container:
        logger.debug(f"Не удалось найти посты в канале '{channel_name}'."
                     "Возможно, делается несколько пересылок и сейчас обрабатываются "\
                     "медиа группы.")
        return []

    post_data = {}
    datetime = message_container.find('a', class_='tgme_widget_message_date').\
                                find('time', class_='time')['datetime']

    post_data['datetime'] = datetime                                
    text_element = message_container.find('div', class_='tgme_widget_message_text')
    text = text_element.get_text(separator='\n', strip=True) if text_element else ""
    post_data['text'] = text

    is_ads = False
    for a_tag in text_element.find_all('a'):
        if a_tag.has_attr('href'):
            link_url = a_tag['href']
            if 'erid' in link_url.lower():
                is_ads = True
                break

    post_data['is_ads'] = is_ads
    media_links = []
    views_element = message_container.find('span', class_='tgme_widget_message_views')
    views_element = parse_count(views_element.text)
    post_data['num_post_views'] = views_element
    media_elements = message_container.find_all('a', class_='tgme_widget_message_photo_wrap') or \
                    message_container.find_all('i', class_='tgme_widget_message_video_thumb')

    for media in media_elements:
        style = media.get('style', '')
        if 'background-image:url(' in style:
            link = style.split("url('")[1].split("')")[0]
            media_links.append(link)
    post_data['media_links'] = media_links

    post_link_element = message_container.find('a', class_='tgme_widget_message_date')
    post_data['post_url'] = post_link_element['href'] if post_link_element else 'N/A'


    reactions_data = {}
    reactions_container = message_container.find('div', class_='tgme_widget_message_reactions')
    if reactions_container:

        reaction_elements = reactions_container.find_all('span', class_='tgme_reaction')

        for reaction in reaction_elements:
            emoji_char = ''
            count_str = ''

            emoji_el = reaction.find('b')
            if emoji_el:
                emoji_char = emoji_el.text.strip()

            full_text = reaction.text.strip()
            if emoji_char:
                count_str = full_text.replace(emoji_char, '').strip()
            else:
                count_str = ''.join(filter(str.isdigit, full_text))

            if emoji_char and count_str:
                reactions_data[emoji_char] = parse_count(count_str)

    post_data['reactions'] = reactions_data
    return post_data
