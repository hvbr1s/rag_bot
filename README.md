## Demo

[![Watch the video](https://img.youtube.com/vi/7H0ideySlVk/maxresdefault.jpg)](https://youtu.be/7H0ideySlVk)

## Intro

SamBot is an AI-powered customer service bot that utilizes Retrieval-Augmented Generation (RAG) to accurately troubleshoot user issues. It is designed for high reliability and low maintenance, with the capability to handle traffic asynchronously.

## How to run the bot locally for testing purposes  

1. Make sure you have the correct `.env` variables: `OPENAI_API_KEY`, `BACKEND_API_KEY`, `API_KEY_NAME`, `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT`, `COHERE_API_KEY`.
2. From the root folder, run `uvicorn app:app --reload --port 8800` to start a local instance of the bot 
3. Using Postman ping the `http://127.0.0.1:8800/gpt` endpoint with a request formatted as follow:

```
POST /gpt HTTP/1.1
Host: <your_url>
Authorization: Bearer <BACKEND_API_KEY>
Content-Type: application/json

{
    "user_input": "your_question",
    "user_locale": "your_locale",
    "user_id": "any_number"
}
```
4.  After a brief moment (10-20 seconds), you should see the bot's response to your question appear in the console. You can test different locales by changing `user_locale` to `eng`, `fr`, etc.

