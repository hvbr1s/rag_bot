## How to update your Pinecone instance  

### Step-by-step  

1. Navigate to the `pinecone_pipeline/update_scripts` folder and run `python3 scraper.py` in the console. This will download all the HC articles and Ledger Academy articles into a `pinecone_pipeline/output_files/articles` folder
2. Stay in the `pinecone_pipeline/update_scripts` folder and run `python3 chunker.py` in the console. This will begin the process of creating labeled chunks of texts from the Academy and HC articles and organize them into a `output.json` file which will also be created in the `pinecone_pipeline/output_files/articles` folder
3. Stay in the `pinecone_pipeline/update_scripts` folder and run `python3 updater.py` in the console. This will begin the process of updating the chunks in `output.json` into our Pinecone `prod` instance.
4. Once the process is over, the words `Database updated!` should appear in the console as well as some statistics about our `prod` Pinecone database inclusing the number of vectors included in each namespace (our `prod` database contains 1 namespace for each supported locale -> `'eng'`, `'fr'` etc). Now delete the `pinecone_pipeline/output_files/` folder containing the scraped articles and `output.json` file. 

### Best practices  

- It's important to update the database every day to keep it up to date.
- When updating, it's important to completely re-scrape both the HC and the Academy to take into account any updates.
- Updating the database does not remove undesirable articles from it. To remove an article from the database, you can use the `deletor.py` script licated in the `pinecone_pipeline/delete_script/` instead.
- After removing an undesirable articles, it's best to add the article number to the `article_ids_to_skip` in the `scraper.py` script