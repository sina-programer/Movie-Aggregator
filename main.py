from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium import webdriver

from abc import ABC, abstractmethod
from collections import UserDict
from concurrent import futures
from threading import Thread
import pygetwindow as gw
import datetime as dt
import configparser
import requests
import shutil
import time
import json
import os

# https://chromedriver.chromium.org/downloads  # with VPN

class Json(UserDict):
    def __init__(self, path, create_template=True):
        super().__init__()

        self.data = {}
        self.path = path

        if create_template:
            self.dump()

    def add(self, key, value):
        self[key] = value

    def adds(self, keys, values):
        for idx in range(len(keys)):
            self[keys[idx]] = values[idx]

    def dump(self, path=None):
        return Json._dump(self.data, path if path else self.path)

    def load(self, path=None):
        self.data = Json._load(path if path else self.path)

    @classmethod
    def _dump(cls, obj, path):
        with open(path, 'w') as handler:
            return json.dump(obj, handler, indent=4)

    @classmethod
    def _load(cls, path):
        with open(path) as handler:
            return json.load(handler)

    def __setitem__(self, key, value):
        self.data[key] = value
        self.dump()


class WebDriver(ABC):
    # EXECUTABLE_PATH = ChromeDriverManager().install()
    EXECUTABLE_PATH = r"Files\chromedriver117.exe"

    def __init__(self, options=[]):
        self.service = Service(WebDriver.EXECUTABLE_PATH)
        self.options = Options()
        for option in options:
            self.options.add_argument(option)

        self.driver = webdriver.Chrome(service=self.service, options=self.options)
        self.tabs = {}  # TODO: manage tabs here

        self.window = gw.getActiveWindow()
        self.window.minimize()

    @property
    @abstractmethod
    def URL(self): return str

    @abstractmethod
    def crawl(self, title): pass

    def download(self, url, path):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                with open(path, 'wb') as handler:
                    return handler.write(response.content)

        except requests.exceptions.SSLError:
            print(f'Downloading <{url}> failed  (turn off your v2ray or system-proxy)')
            return None

    def wait(self, delay=1):
        self.driver.implicitly_wait(delay)

    def go(self, url, delay=2):
        self.driver.get(url)
        self.wait(delay)

    def reload(self, delay=2):
        self.driver.get(self.driver.current_url)
        self.wait(delay)

    def new_tab(self, url, key):
        self.driver.execute_script(f"window.open({url}, {key});")
        self.tabs[key] = url

    def switch_tab(self, key):
        self.driver.switch_to.window(key)

    def windows(self):
        return self.driver.window_handles

    def title(self):
        return self.driver.title


class WebDriverThread(Thread, WebDriver, ABC):
    def __init__(self, options=[]):
        WebDriver.__init__(self, options)
        Thread.__init__(self)

        self._crawl = self.crawl

    def run(self):
        self._crawl(self.title)

    def crawl(self, title):
        self.title = title
        self.start()


class IMDB(WebDriver):
    URL = r"https://www.imdb.com"

    def crawl(self, title):
        if self.driver.current_url != IMDB.URL:
            self.go(IMDB.URL, delay=4)

        self.driver.find_element(By.ID, "suggestion-search").send_keys(title)
        self.driver.find_element(By.ID, "suggestion-search-button").click()
        page_url = self.driver.find_element(By.CLASS_NAME, "ipc-metadata-list").find_element(By.TAG_NAME, 'li').find_element(By.TAG_NAME, 'a').get_attribute('href')
        self.go(page_url)

        # The main movie page
        name = self.driver.find_element(By.TAG_NAME, 'h1').text
        folder_path = os.path.join(PATH, name)
        if not os.path.exists(folder_path):
            os.mkdir(folder_path)

        idx = TITLES.index(title)
        NAMES[idx] = name
        filename = FILES[idx]

        data = Json(os.path.join(folder_path, 'data.json'))
        data['name'] = name

        genres = self.driver.find_element(By.CLASS_NAME, 'ipc-chip-list').find_elements(By.TAG_NAME, 'span')
        genres = list(map(lambda span: span.text, genres))
        data['genres'] = genres

        rating = self.driver.find_element(By.XPATH, r"//a[@aria-label='View User Ratings']/span/div/div[2]/div/span").text
        data['rating'] = rating

        year = self.driver.find_elements(By.TAG_NAME, 'ul')[13].find_element(By.TAG_NAME, 'a').text
        data['year'] = year

        cover_path = os.path.join(folder_path, 'cover.png')
        data['cover-path'] = cover_path
        # self.driver.find_element(By.CLASS_NAME, 'ipc-poster').screenshot(cover_path)
        self.driver.find_element(By.CLASS_NAME, 'ipc-poster').click()
        self.wait(2)
        cover = self.driver.find_element(By.CLASS_NAME, 'media-viewer').find_element(By.TAG_NAME, 'img')
        while not self.download(cover.get_attribute('src'), cover_path):
            time.sleep(1)

        data.dump()

        source = os.path.join(PATH, filename)
        destination = os.path.join(folder_path, filename)
        Thread(target=shutil.move, args=(source, destination)).start()



def get_movie_name(name):
    if ' - ' in name:
        return name.split(' - ', 1)[0]
    return os.path.splitext(name)[0]


CONFIG_PATH = 'config.ini'
ENCODING = 'utf-8'

if __name__ == "__main__":
    options = ['ignore-certificate-errors', 'ignore-ssl-errors']
    config = configparser.ConfigParser()

    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH, encoding=ENCODING)
        print(f"Configs are successfully imported from: <{CONFIG_PATH}>")
    else:
        print(f'ERROR: the file {CONFIG_PATH} does not exist!')
        exit()

    PATH = os.path.normpath(config['General']['PATH'])
    MAX_THREADS = int(config['General']['MAX_THREADS'])
    FILES = os.listdir(PATH)
    TITLES = list(map(get_movie_name, FILES))
    NAMES = TITLES.copy()

    if MAX_THREADS == 0:
        MAX_THREADS = len(TITLES)

    if not os.path.exists(PATH):
        print(f"ERROR: the path you want to scrape is not available! ({CONFIG_PATH}[General][PATH])")
        exit()

    with futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        for title in TITLES:
            executor.submit(IMDB(options).crawl, title)

    print(f"All below movies are done!")
    print(NAMES)
