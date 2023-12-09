import os
import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import shutil
from datetime import date

load_dotenv()
ZD_USER = os.getenv("ZD_USER")
ZD_PASSWORD = os.getenv("ZD_PASSWORD")
# Check to make sure neither environment variable is missing
assert ZD_USER and ZD_PASSWORD, "Make sure your environment variables are populated in .env"

def create_metadata_string(metadata: dict):
    metadata_string = ''
    for key, value in metadata.items():
        metadata_string += f'<meta name="{key}" content="{value}"/>'
    return metadata_string


def clean_and_save_html(article_url, output_folder):
    response = requests.get(article_url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract the <article> tag
    article_tag = soup.find('article')
    tokenized_url = article_url.split('/')
    article_title = ''
    for token in tokenized_url[::-1]:
        if token:
            article_title = token
            break

    if not article_tag:
        print(f"No <article> tag found in {article_url}")
        return
    
    # get the locale from the "lang" attribute inside the html tag
    article_locale = soup.find('html').get('lang', 'unknown')
    metadata = {
        'source': article_url,
        'source-type': 'academy',
        'locale': article_locale,
        'zd-article-id': 'N/A',
        'title': article_title.replace('-', ' '),
        'classification': 'public'
        }

    # Create a new BeautifulSoup object for cleaned content
    cleaned_soup = BeautifulSoup('<html><head></head><body></body></html>', 'html.parser')

    # Add the metadata to the cleaned_soup's <head> tag
    cleaned_soup.head.append(BeautifulSoup(create_metadata_string(metadata), 'html.parser'))

    # Append the <article> tag to the cleaned_soup's <body> tag
    cleaned_soup.body.append(article_tag)

    # Save the cleaned HTML content to a file
    output_filename = article_title.replace('-', '_')
    filename = os.path.join(output_folder, f'{output_filename}_{article_locale}.html')
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(str(cleaned_soup.prettify()))

def scrape_zendesk(output_folder: str, article_ids_to_skip: list = None, zendesk_base_url: str = 'https://ledger.zendesk.com', locales: list = None, scrape_these_article_ids: list = None):
    if isinstance(locales, list):
        valid_locales = ['en-us', 'fr-fr', 'ru', 'zh-cn', 'es', 'ar', 'de', 'tr', 'ko', 'ja', 'pt-br']
        locales = [locale for locale in locales if locale in valid_locales] # filter out any invalid locales
    if not locales:
        # default to all locales if no locales are provided, or if the filtered list ends up empty
        locales = ['en-us', 'fr-fr', 'ru', 'zh-cn', 'es', 'ar', 'de', 'tr', 'ko', 'ja', 'pt-br']
    if not article_ids_to_skip:
        article_ids_to_skip = []
    endpoints = [(locale, f'{zendesk_base_url}/api/v2/help_center/{locale.lower()}/articles.json') for locale in locales]
    for locale, endpoint in endpoints:
        while endpoint:
            response = requests.get(endpoint, auth=(ZD_USER, ZD_PASSWORD))
            assert response.status_code == 200, f'Failed to retrieve articles with error {response.status_code}'
            data = response.json()
            for article in data['articles']:
                if scrape_these_article_ids and article['id'] not in scrape_these_article_ids:
                    # If this argument is provided, then we only want to scrape the articles in the provided list
                    continue
                if not article['body'] or article['draft'] or article['id'] in article_ids_to_skip:
                    continue
                title = '<h1>' + article['title'] + '</h1>'
                url = article['html_url']
                metadata = {
                    'source': url,
                    'source-type': 'zendesk',
                    'locale': locale,
                    'zd-article-id': article['id'],
                    'title': article['title'],
                    'classification': 'public'
                    }
                filename = f"zd_{article['id']}_{locale}.html"
                with open(os.path.join(output_folder, filename), mode='w', encoding='utf-8') as f:
                    f.write(f'<!DOCTYPE html><html><head>{create_metadata_string(metadata)}</head>\
                            <body>{title}\n{article["body"]}</body></html>')
                print(f"{article['id']} copied!")

            endpoint = data['next_page']

def scrape_urls(output_folder, url_txt_file_path):
    # Read article URLs from the text file
    with open(url_txt_file_path, 'r') as file:
        article_urls = [line.strip() for line in file]

    for url in article_urls:
        #if url.startswith('https://www.ledger.com/academy/tutorials/') or url.startswith('#') or url.startswith('https://www.ledger.com/academy/school-of-block/'):
        if url.startswith('https://www.ledger.com/fr/academy/tutorials/') or url.startswith('#') or url.startswith('https://www.ledger.com/fr/academy/school-of-block/') or url.startswith('https://www.ledger.com/fr/academy/mediatheque/page/') :    
            # Cut out all of the academy tutorials, and also any lines in the file that begin with #
            # This will allow someone to add a comment to this file
            # or comment out particular articles that are problematic if necessary
            print(f"Skipped: {url}")
            continue
        clean_and_save_html(url, output_folder)

def scrape_other_articles(output_folder, source_directory):
    # get a list of files in the source directory
    files = os.listdir(source_directory)

    # loop through the files and copy them to the destination directory
    for file in files:
        src_file = os.path.join(source_directory, file)
        dst_file = os.path.join(output_folder, file)
        shutil.copy(src_file, dst_file)

    print("Other articles copied successfully.")

def run_scraper(output_directory_path: str = None, url_txt_file_path: str = None, other_articles_directory_path: str = None, locales: list = None, scrape_these_article_ids: list = None):
    # Set some defaults if not provided
    if not output_directory_path:
        pinecone_pipeline_root_directory = os.path.dirname(os.path.dirname(__file__))
        output_directory_path = os.path.join(pinecone_pipeline_root_directory, 'output_files')
    if not url_txt_file_path:
        #url_txt_file_path = os.path.join(output_directory_path, '..', 'url.txt') # Use this to download the ENG Academy
        url_txt_file_path = "/home/danledger/knowledge_bot/pinecone_pipeline/url_fr.txt" # Use this to download the FR Academy
    if not other_articles_directory_path:
        other_articles_directory_path = os.path.join(output_directory_path, '..', 'other_articles')
    scraper_output_folder = os.path.join(output_directory_path, 'articles')

    # clear out any files that might be there, and create the folders if they don't exist.
    if os.path.exists(scraper_output_folder):
        shutil.rmtree(scraper_output_folder)
    os.makedirs(scraper_output_folder, exist_ok=True)
    if scrape_these_article_ids:
        # If we're only scraping specific articles, then we only need to run the Zendesk part of the scraper
        scrape_zendesk(scraper_output_folder, article_ids_to_skip=[], scrape_these_article_ids=scrape_these_article_ids, locales=locales)
    else:
        scrape_zendesk(scraper_output_folder, article_ids_to_skip=[
            360015559320,   # (ENG/FR/SPA/GER) E-COMMERCE AND MARKETING DATA BREACH - FAQ
            9731871986077,  # HOW TO EXPORT YOUR SAMSUNG MX1 GENESIS/ART NFT TO METAMASK AND SECURE IT WITH A LEDGER WALLET
            9746372672925,  # LEDGER EXTENSION CHECKER: HOW TO INTERPRET WARNING MESSAGES
            360000105374,   # LEDGER BLUE MANUAL
            360006284494,   # TROUBLESHOOT LEDGER BLUE FIRMWARE UPDATE
            7410961987869,  # ARTIST'S GUIDE TO MIGRATING TO LEDGER
            360033473414,   # OLED SCREEN VULNERABILITY - FAQ
            4404388633489,  # EXPORT YOUR ACCOUNTS
            360015738179,   # DERIVATION PATH VULNERABILITY IN BITCOIN DERIVATIVES
            360034576433,   # BLUETOOTH PROTOCOL VULNERABILITY
            12833652732573, # CONNECT YOUR LEDGER TO BASE (BASE) NETWORK VIA METAMASK
            5692126348957,  # MY CARDANO (ADA) BALANCE DISPLAYS 0
            5705495569949,  # FTX SWAPS TEMPORARILY PAUSED IN LEDGER LIVE
            360021144618,   # WYRE BUY SERVICE TEMPORARILY PAUSED IN LEDGER LIVE
            4404422869265,  # WYRE SWAPS TEMPORARILY PAUSED IN LEDGER LIVE
            10126075005981, # CONNECT YOUR LEDGER TO COREUM MAINNET
            6563476062621,  # ETHEREUM MERGE LIVE THREAD
            9982370871069,  # WHAT IS THE ETHEREUM SHANGHAI UPGRADE AND HOW WILL IT AFFECT LEDGER LIVE USERS
            4405497803153,  # MCU FIRMWARE IS NOT GENUINE
            115005456969,   # BITCOIN GOLD
            4405497803153,  # MCU FIRMWARE IS NOT GENUINE
            4405495141393,  # MCU FIRMWARE IS OUTDATED
            9093172893597,  # VALENTINE DAY
            115005199449,   # SET UP MYCELIUM ON ANDROID
            4413120085393,  # WHY IS THERE A STICKER ON THE BACK OF THE BOX?
            4413120085393,  # WHY IS THERE A STICKER ON THE BACK OF THE BOX?
            360012650219,   # DOES COVID-19 IMPACT SHIPPING?
            13692339908893, # HOW TO STAKE ETH THROUGH LEDGER LIVE [ AND CHOOSE THE OPTION THAT WORKS BEST FOR YOU]
            15090727186077, # TEMPORARY ISSUE WITH BITCOIN (BTC)
            14593285242525, # SOLVING THE "TXN-MEMPOOL-CONFLICT" ERROR WHEN SENDING BTC
            4404130736401,  # TRON SYNCHRONIZATION ISSUE WITH LEDGER LIVE 2.30.0
            
            ],
            locales = locales)
        #scrape_urls(scraper_output_folder, url_txt_file_path)
        scrape_other_articles(scraper_output_folder, other_articles_directory_path)

if __name__ == "__main__":
    #run_scraper(locales=['en-us'])
    run_scraper(locales=['fr-fr'])
