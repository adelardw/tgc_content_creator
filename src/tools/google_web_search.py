from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from icrawler.builtin import GoogleImageCrawler
from icrawler import ImageDownloader
import requests

from loguru import logger
from src.tools.config import CX_ID, GOOGLE_API_KEY


def search_img(query: str, num: int = 10):
    try:
        permissive_rights = 'cc_publicdomain|cc_attribute|cc_sharealike'
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        res = service.cse().list(q=query,cx=CX_ID,
                                 searchType='image',
                                 fileType='jpg,png,jpeg,gif',
                                 safe='active',
                                 gl='ru',
                                 num=num,
                                 fields="items/link"
                                 ).execute()


        answer = []
        if 'items' in res:
            for item in res['items']:
                answer.append(item['link'])

        return answer
    except Exception as e:
        if e.status_code == 429:
            logger.info("Ошибка: Дневная квота на запросы к Google Custom Search API исчерпана.")
            return [] 
        else:
            logger.info(f"Произошла ошибка HTTP: {e}")
            return []
        





class LinkCollectorGoogleImageCrawler(GoogleImageCrawler):
    def __init__(self, *args, **kwargs):
        super().__init__(downloader_cls=LinkCollectorDownloader, *args, **kwargs)
        self.image_links = []


class LinkCollectorDownloader(ImageDownloader):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_links = []
        self.counter = 0


    def download(self, task, default_ext=None, timeout=5, max_retry=1, overwrite=False, **kwargs):
        """Переопределенный метод - только сохраняет ссылку, не скачивает файл"""
        file_url = task['file_url']

        if self.counter == self.max_num:
            return True
        try:
            response = requests.head(file_url, timeout=2, allow_redirects=True)
            if response.status_code == 200:
                self.image_links.append(file_url)
                self.counter += 1
        except requests.RequestException as e:
            logger.info(f"✗ Ошибка проверки ссылки: {file_url} - {e}")


        return True

    def get_links(self):
        """Возвращает собранные ссылки"""
        return self.image_links



def get_google_image_links(keyword, max_num=5, filters=None):
    """Функция для получения списка ссылок на изображения"""

    crawler = LinkCollectorGoogleImageCrawler()

    crawler.crawl(
        keyword=keyword,
        max_num=max_num,
        language='ru',
        filters=filters
    )
    return crawler.downloader.get_links()

