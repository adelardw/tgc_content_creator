from ddgs import DDGS
import requests
import random
import os
from dotenv import load_dotenv
load_dotenv()
from bs4 import BeautifulSoup
from langchain_qdrant.qdrant import QdrantVectorStore,QdrantClient
from langchain_core.documents import Document
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from loguru import logger
from src.tools.config import web_retrieve_kwargs, embed_model_name, user_agents
from src.tools.utils import is_url_safe


class DuckDuckGoOnlineRAG:
    '''
    Интрументы для поиска информации с помощью duck-duck go
    и парсинга max_results найденных источников
    '''
    model_kwargs = {'device': 'cpu'}
    encode_kwargs = {'normalize_embeddings': True}
    forbidden_links = {'youtube','video','shorts','instagram','inst','meta','facebook','twitter',
                       'vk','t.me'}
    def __init__(self,
                 embed_model: str = os.getenv('EMBED_MODEL','cointegrated/LaBSE-en-ru'),
                 max_search_results: int = 5,
                 n_chunks: int = 3,
                 chunk_size: int = 650,
                 chunk_overlap: int = 150):

        self.max_search_results = max_search_results
        self.n_chunks = n_chunks
        self.ts = RecursiveCharacterTextSplitter(chunk_overlap=chunk_overlap, chunk_size=chunk_size)
        self.search = DDGS()
        self.embed = HuggingFaceEmbeddings(model_name=embed_model,
                                           model_kwargs=self.model_kwargs,
                                           encode_kwargs=self.encode_kwargs)


    def _web_search(self, query: str) -> list[dict[str, str]]:
        '''
        Поисковик на движке duck-duck-go. Позволяет находить любую информацию в интернете.
        по данному запросу - query.
        Возвращает список из max_results словарей.
        Каждый словарь имеет ключи: 'title', 'href', 'body'
        'href' содержит url (ссылку) на страницу которую можно будет спарсить
        '''
        logger.info(query)
        return self.search.text(query, max_results=self.max_search_results)


    def _parse_site(self, url: str):
        '''
        Парсит сайт по заданной ссылке (url)
        '''

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.5',
                                'Accept-Encoding': 'gzip, deflate',
                                'DNT': '1',
                                'Connection': 'keep-alive',
                                'Upgrade-Insecure-Requests': '1',
                                'Sec-Fetch-Dest': 'document',
                                'Sec-Fetch-Mode': 'navigate',
                                'Sec-Fetch-Site': 'none',
                                'Sec-Fetch-User': '?1'}
        headers['User-Agent'] = random.choice(user_agents)
        try:
            resp = requests.get(url, headers=headers,timeout=120)
            bs = BeautifulSoup(resp.content,'html.parser')
            for tag in bs(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()

            main_content = (bs.find('main') or
                            bs.find('article') or
                            bs.find('div', {'id': 'content'}) or
                            bs.find('div', {'class': 'content'}) or
                            bs.find('div', {'id': 'main-content'}) or
                            bs.find('div', {'class': 'post-body'}) or
                            bs.find('div', {'class': 'article-body'}))

            if not main_content:
                main_content = bs.body

            if not main_content:
                return None


            text = main_content.get_text(separator=' ', strip=True)
            return text
        except Exception as e:

            return

    def _make_vector_storage(self, documents: list[Document], query: str):
        '''
        Создаёт или находит VS, добавляя в неё новые документы из поиска
        '''

        self.storage = QdrantVectorStore.from_documents(documents=documents,
                                                            embedding=self.embed,
                                                            url="http://localhost:6333",
                                                            collection_name=query,
                                                            )

    def _make_docs(self, query: str):
        '''
        Создает / Обновляет Vector Storage
        '''
        docs = []
        search_res = self._web_search(query)

        for results in search_res:
            metadata = {'title': results.get('title', 'NoTitle'),
                        'body': results.get('body','UnavailableBody')}
            href = results['href']
            checl_url = is_url_safe(href)
            if not checl_url:
                continue
            for l in self.forbidden_links:
                if l in href:
                    next_link = True
                    break
                else:
                    next_link = False

            if next_link:
                continue

            text = self._parse_site(href)
            if text:
                doc = Document(page_content=text.replace('\n',' ').encode(encoding='utf-8'), metadata=metadata)
                docs.append(doc)

        return self.ts.split_documents(docs)

    @staticmethod
    def _prepare_ctx(chunks: list[Document]) -> str:
        ctx_msg = ''
        for i, ctx in enumerate(chunks):
            ctx_msg += f'Контекстный чанк № {i}: {ctx.page_content};'

        return ctx_msg


    def __call__(self, query: str, *args, **kwds):
        qc = QdrantClient('http://localhost:6333')
        docs = self._make_docs(query)
        self._make_vector_storage(docs, query)
        logger.info('Коллекция успешно создана!')


        context_chunks = self.storage.similarity_search(query,
                                                        k=self.n_chunks,
                                                        *args,
                                                        **kwds)
        qc.delete_collection(query)
        return self._prepare_ctx(context_chunks)



retriever =DuckDuckGoOnlineRAG(embed_model=embed_model_name,
                               **web_retrieve_kwargs)
