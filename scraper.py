import requests
import time
import os
import json
import glob
from bs4 import BeautifulSoup
from definitions import *


class DojNewsScraper():
    """Scrapes the DOJ press release website for links to all releases and 
    saves the content as JSON files

    Scraper visits the main Breifing Room page located at 
    https://www.justice.gov/news and identifies the max number of pages based
    on the Last button at the bottom of the page. Each page is then iterated
    from 0 to N and the urls for all releases are captured into links.txt.

    Links.txt is then iterated where each url is parsed and saved as a JSON
    object in the data/ folder. Only releases labeled as "Press Release" are
    saved. Some releases are speech transcripts, and these are ignored."""

    def __init__(self, sleep_time=1.5):
        self.url = 'https://www.justice.gov'
        self.dir = 'data/'
        self.sleep_time = sleep_time

        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

    def _format_page_url(self, page_num):       
        return '{}/news?page={}'.format(self.url, page_num)

    def _get_page_content(self, url):
        return requests.get(url).content

    def _get_page_filename(self, url):
        return '{}{}.json'.format(self.dir,url.replace('/','_'))

    def _save_page(self, filename, data):
        with open(filename, 'w') as file:
            json.dump(data, file)

    def get_page_links(self, start_page=0):
        """Gets links to press releases from /news

        Scrapes the DOJ Breifing Room page for a list of press releases. The
        Last button is read to determine how many pages need to be scanned.
        Each detected URL is saved to links.txt. Alerts are fired if a link
        already exists. Duplicate entries are not added to links.txt.

        Scraper stops if two consecutive pages contain duplicate links. This
        helps if you are incrementally scraping for latest results.

        Args:
            start_page: Sets the starting page for the scrape if need to resume
                from a later point        
        """

        # Load links.txt into memory if it exists saving a copy of it
        if os.path.exists('links.txt'):
            os.rename('links.txt', 'links.txt.old')

            with open('links.txt.old', 'r') as file:
                urls = file.read().splitlines()
        else:
            urls = []

        # Scrape the first news page and get the count from the LAST PAGE link
        content = self._get_page_content(self._format_page_url(start_page))
        page_data = BeautifulSoup(content, 'lxml')
        
        total_page_count = int(page_data.find('a', MAIN_PAGE_LAST)['href']\
            .split('=')[1])
        print('Found {} pages'.format(total_page_count))

        current_page = start_page
        continue_loop = True
        consecutive_duplicates = 0

        # Note: Some pages were missing like 311 and 475 at the time I wrote this
        # Loop over each page which contains 25 links per page
        while continue_loop:
            releases = page_data.find_all('div', MAIN_PAGE_RELEASE)
            add_count = 0
            skip_count = 0

            for release in releases:
                url = release.find('a')['href']

                if url in urls:
                    skip_count += 1
                else:
                    urls.append(url)
                    add_count += 1

            print('Appended {} releases on page {}/{}. Skipped {}'\
                .format(add_count, current_page, total_page_count, skip_count))

            # Don't allow code to continue when two consecutive pages with
            # duplicates have been loaded
            
            if skip_count > 0:
                consecutive_duplicates += 1
            else:
                consecutive_duplicates = 0

            current_page += 1
            time.sleep(self.sleep_time)
            
            if (current_page > total_page_count) or (consecutive_duplicates==2):
                continue_loop = False
            else:
                content = self._get_page_content(self._format_page_url(current_page))
                page_data = BeautifulSoup(content, 'lxml')

        print('Writing {} urls to links.txt'.format(len(urls)))
        
        with open('links.txt', 'w') as file:
            file.writelines('\n'.join([u for u in urls]))

    def get_page_detail(self):
        """Parses press releases into JSON files

        Reads links.txt and attempts to download a copy of each press release
        locally. The page is opened and parsed with BeautifulSoup for elements
        such as:
            -Id (Release ID given by DOJ, if any)
            -Title (Title of release)
            -Contents (Text of release)
            -Date (Published date)
            -Topics (Topic(s), if any are listed)
            -Components (Related agencies / departments, if any)

        Files are saved using the URL in the file name. If a file is detected
        in the data directory, then the scrape is skipped."""

        with open('links.txt', 'r') as file:
            urls = file.read().splitlines()
        url_count = len(urls)

        for i, url in enumerate(urls):
            if '/speech/' in url:
                print('Skipping speech {}'.format(url))
                continue

            filepath = self._get_page_filename(url)

            if os.path.exists(filepath):
                print('{} already exists'.format(filepath))
                continue

            print('Scraping {} of {}'.format(i, url_count))

            # Get main page elements
            data = BeautifulSoup(self._get_page_content(self.url + url), 'lxml')
            page_text = ' '.join([p.text for p in data.find('div', PAGE_TEXT).find_all('p')])
            page_title = data.find('h1', PAGE_TITLE).text
            page_date = data.find('span', PAGE_DATE)['content']

            # Check topics (optional)
            topics = data.find('div', PAGE_TOPIC_LIST)
            page_topics = []
            if topics:
                page_topics = [topic.text for topic in topics.find_all('div', PAGE_TOPIC)]

            # Check components (optional)
            components = data.find('div', PAGE_COMPONENT_LIST)
            page_components = []
            if components:
                page_components = [component.text for component in components.find_all('a')]

            # Check page id (suprisingly, optional)
            pg_id = data.find('div', PAGE_ID_CONTAINER)
            page_id = None

            if pg_id:
                page_id = pg_id.find('div', PAGE_ID).text

            data = {
                'id': page_id,
                'title': page_title,
                'contents': page_text,
                'date': page_date,
                'topics': page_topics,
                'components': page_components
            }

            self._save_page(filepath, data)
            time.sleep(self.sleep_time)

    def combine_outputs(self):
        "Combines all JSON files in data dir into a single newline JSON"

        i = 0
        with open('combined.json', 'w') as master_file:
            files = glob.glob('{}*.json'.format(self.dir))
            print('Loading {} files'.format(len(files)))

            for file_path in files:
                with open(file_path, 'r') as json_file:
                    master_file.write(json_file.read() + '\n')
                    i += 1
                
                if i % 1000 == 0:
                    print('...loaded {}/{}'.format(i, len(files)))
                

        print('Combined {} files into combined.json'.format(i))


    def scrape(self, start_page=0):
        "Easy wrapper for scrape job"
        self.get_page_links(start_page=start_page)
        self.get_page_detail()
        self.combine_outputs()

if __name__ == '__main__':
    scraper = DojNewsScraper()
    scraper.scrape()

