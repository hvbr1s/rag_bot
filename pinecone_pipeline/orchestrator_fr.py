from update_scripts_fr import  scraper_fr, chunker_fr, updater_fr
from os import path
import shutil

if __name__ == "__main__":
    # Set some default paths
    pinecone_pipeline_root_directory = path.dirname(__file__)
    output_directory = path.join(pinecone_pipeline_root_directory, 'output_files')
    url_txt_file_path = path.join(pinecone_pipeline_root_directory, 'url.txt')
    other_articles_directory_path = path.join(pinecone_pipeline_root_directory, 'other_articles')

    # Run the pipeline
    scraper_fr.run_scraper(output_directory, url_txt_file_path, other_articles_directory_path, locales=['fr-fr'],
                        # If you want to scrape specific Zendesk article IDs, put them in this list.
                        # Otherwise, leave it empty and it will scrape everything.
                        scrape_these_article_ids=[
                            4404389171985,
                        ]
                        )
    output_json_path = chunker_fr.run_chunker(
        output_directory,
        chunk_size=500
        )
    # We likely don't need to reboot the index anymore, but I'm leaving this here just in case
    #index_booter.reboot_index('prod')
    updater_fr.run_updater(output_json_path, 'prod')

    # Delete the output_files directory
    if path.exists(output_directory):
        shutil.rmtree(output_directory)
        print(f"Deleted the folder: {output_directory}")
    else:
        print(f"The folder {output_directory} does not exist.")

print('Update complete!')