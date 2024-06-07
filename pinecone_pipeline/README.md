## How to update Pinecone 

We're currently running 2 Pinecone instances.

Our **main** Pinecone instance is `serverless-test`.

Our **backup** Pinecone instance is `prod`.

### Step-by-step  

1. Navigate to the `pinecone_pipeline/update_scripts` folder and open the `semantic_orchestrator.py` script.
2. In the script, navigate to the list named `scrape_these_article_ids` which is nested inside the `scraper.run_scraper()` function.
3. Copy-paste the ID of the article to update or upload then save the modified `emantic_orchestrator.py`.
4. Run `semantic_orchestrator.py` by typing `python3 semantic_orchestrator.py` into your terminal.

If everything goes well, the script will update both our main and our backup database. If so, the terminal will display `Main database updated!` and `Backup database updated!` along with statistics about each database including the number of vectors in each.

### Best practices  

- It's important to update the databases **every day** to keep them up to date.
- Updating the database does not remove undesirable articles from it. To remove an article from the database, you will need to run `semantic_id_lookup.py` located in `pinecone_pipeline/id_lookup/` to obtain the chunk's ID then manually search and delete the chunk and other related chunks in both databases in Pinecone.
- After removing an undesirable articles, it's best to add the article number to the `blacklist_module.py` script in the `blacklist`directory under `pinecone_pipeline`.