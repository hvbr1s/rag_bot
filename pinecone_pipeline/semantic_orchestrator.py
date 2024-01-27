from update_scripts import  scraper, semantic_chunker, semantic_updater
from blacklist import blacklist_module
from os import path
import shutil

if __name__ == "__main__":
    # Set some default paths
    pinecone_pipeline_root_directory = path.dirname(__file__)
    output_directory = path.join(pinecone_pipeline_root_directory, 'output_files')
    url_txt_file_path = path.join(pinecone_pipeline_root_directory, 'url.txt')
    other_articles_directory_path = path.join(pinecone_pipeline_root_directory, 'other_articles')

    # Run the pipeline
    scraper.run_scraper(output_directory, url_txt_file_path, other_articles_directory_path, locales=['en-us'],
                        # If you want to scrape specific Zendesk article IDs, put them in this list.
                        # Otherwise, leave it empty and it will scrape everything.
                        scrape_these_article_ids=[

                            115003797194,

                        ]
                        )
    output_json_path = semantic_chunker.run_chunker(
        output_directory,
        chunk_size=512
        )
    # We likely don't need to reboot the index anymore, but I'm leaving this here just in case
    #index_booter.reboot_index('prod')

    # Update Pinecone database
    semantic_updater.run_updater(output_json_path)

    # Delete the output_files directory
    if path.exists(output_directory):
        shutil.rmtree(output_directory)
        print(f"Deleted the folder: {output_directory}")
    else:
        print(f"The folder {output_directory} does not exist.")

print('Update complete!')