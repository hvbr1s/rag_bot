## How to run the bot locally for testing purposes  

1. Make sure you have the correct `.env` variables: `OPENAI_API_KEY`, `BACKEND_API_KEY`, `API_KEY_NAME`, `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT`
2. From the root folder, run `uvicorn app:app --reload --port 8800` to start a local instance of the bot 
3. Using Postman ping the `http://127.0.0.1:8800/gpt` endpoint with a request formatted as follow:

```
POST /gpt HTTP/1.1
Host: knowlbot.aws.stg.ldg-tech.com
Authorization: Bearer <BACKEND_API_KEY>
Content-Type: application/json

{
    "user_input": "your_question",
    "user_locale": "your_locale",
    "user_id": "any_number"
}
```
4.  After a brief moment (10-20 seconds), you should see the bot's response to your question appear in the console. You can test different locales by changing `user_locale` to `eng`, `fr`, etc.


## How to deploy a new STG version

Any new code pushed to the `main` branch will automatically trigger a new deployment to STG. The SamanthaBot Slack channel is directly connected to STG so it's the best place to check if things are working as intended before a new PRD release is deployed to our customers.

When testing locales other than `eng`, use Postman to ping the `https://knowlbot.aws.stg.ldg-tech.com/gpt` endpoint using the same format a described in the previous section to verify that things are working as expected.

## How to deploy a new PRD version

It's strongly recommended to test things out on STG before deploying new code to PRD. Once you're happy with your testing, follow these instructions to deploy a new version to PRD.

1. Open the `values.yaml` file located in `argocd/prd/` (make sure you're looking at the `prd` file and not the `stg` file)
2. Go to `tag` and change the version number. For example `v1.3.2` to `v1.4.0`
3. Push your code to the `main` branch and wait for it to be deployed.
4. Open github and navigate to `Releases > Draft a new release`. Then create a new tag which has the same value as the tag in the `values.yaml` file you just mofified. Give your release a title and a description then click `Public release`. This will automatically trigger a new deployment to PRD.
5. Importantly, make sure to set your new release as `latest release` and not as a `pre-release` by tickin the appropriate box on Github.
6. Once the new code is deployed to PRD, use Postman to ping `https://knowlbot.aws.prd.ldg-tech.com/gpt` as described above to make sure everything is working as intented.

Congratulations, you've succesfully deployed your code to PRD!