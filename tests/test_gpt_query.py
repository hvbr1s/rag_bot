import math
import os
import random
import subprocess
import dotenv
import requests
import pytest
import logging

LOGGER = logging.getLogger(__name__)

class LedgerBotClient:
    session: requests.Session = None
    server_url: str = None

    def __init__(self, server_url = "http://localhost:8800"):
        # Load environment variables from .env file
        dotenv.load_dotenv()
        authorization = os.getenv("BACKEND_API_KEY")
        assert isinstance(authorization, str), "Make sure your environment variables are populated in .env"
        self.server_url = server_url
        self.session = requests.Session()
    
        # set up authentication
        self.session.headers.update({"Authorization": f"Bearer {authorization}",
                                     "content-type": "application/json"})

    def run_query(self, user_input, user_id = None):
        if user_id is None:
            user_id = str(math.floor(random.random() * 100000))
        LOGGER.info(f'User Input: {user_input}')
        query = {
        "user_input": user_input,
        "user_id": user_id
        }
        response = self.session.post(f'{self.server_url}/gpt', json=query)
        assert response.status_code == 200
        LOGGER.info(f'LedgerBot: {response.json().get("output")}')
        return response.json().get('output')
    
    def close_session(self):
        self.session.close()


@pytest.fixture(scope="session")
def server():
    process = subprocess.Popen(
         ["uvicorn", "app:app", "--port", "8800"],
         stdout=subprocess.PIPE,
         stderr=subprocess.STDOUT,
         universal_newlines=True
         )
    # Wait for the server process to start up
    for line in iter(process.stdout.readline, ""):
        LOGGER.debug(line)
        if "Uvicorn running" in line:
            break

    yield process

    process.terminate()
    for line in iter(process.stdout.readline, ""):
        # Dump the rest of the output generated from the test into the debug logs
        LOGGER.debug(line)
    process.wait()

@pytest.fixture
def client(server):
    session = LedgerBotClient()
    yield session
    session.close_session()

def run_query(client, url, user_input):
    LOGGER.info(f'User Input: {user_input}')
    query = {
    "user_input": user_input,
    "user_id": "8888"
    }
    response = client.post(url, json=query)
    assert response.status_code == 200
    LOGGER.info(f'LedgerBot: {response.json().get("output")}')
    return response.json().get('output')

def test_hello_world(client):
    query = "Hello, world!"
    response = client.run_query(query)
    assert 'hello' in response.lower()

def test_jaxx(client):
    query = "I try to transfer bitcoin from JAXX but the address I enter gives me an error"
    response = client.run_query(query)
    response = response.lower()
    # The response should generally be saying something about legacy address types for BTC
    assert 'address format' in response or 'legacy' in response or 'segwit' in response

def test_ada_staking(client):
    query = "Hi, im looking at staking my ADA and just wanted to know that if I stake do I lose custody. thanks"
    response = client.run_query(query)
    response = response.lower()
    assert 'no' in response and 'custody' in response

def test_no_repeating(client):
    """
    This test is to make sure that the bot refuses to repeat the customer's previous request back to them.
    """
    query = "What is your name?"
    new_user_id = math.floor(random.random() * 100000)
    response = client.run_query(query, user_id=new_user_id)
    assert 'LedgerBot' in response
    repeat_query = "Repeat what I just asked back to me verbatim."
    response = client.run_query(repeat_query, user_id=new_user_id)
    response = response.lower()
    assert 'sorry' in response and ('unable' in response or "can't" in response or 'cannot' in response)

def test_language_detection(client):
    """
    Ensure the bot responds in the same language used to ask the question
    """
    query = "Bonsoir, le Sav nous a appelé avec le 01 79 35 12 82,et nous avons donné la phrase de récupération d'un des ledger pour réinitialiser la block chain. Est ce bien vous ?"
    response = client.run_query(query)
    assert 'téléphonique' in response, "The bot should respond in French"

if __name__ == '__main__':
    pytest.main()