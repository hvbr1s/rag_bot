
import os
from crewai import Agent
from crew.tool import retriever_tool
from langchain.agents import load_tools

os.environ["OPENAI_MODEL_NAME"]="gpt-4o"

# Creating a senior researcher agent with memory and verbose mode
researcher = Agent(
  role='Senior Researcher',
  goal='ALWAYS use your Knowledge Base tools to find solutions to technical questions about Ledger products.',
  verbose=True,
  memory=True,
  backstory=(
    """
      Driven by curiosity, you're at the forefront of cybersecurity applied to blockchain and an expert in Ledger products including the Ledger Nano S Plus, Nano X, Ledger Stax and the Ledger Live app.
      
    """
  ),
  tools=[retriever_tool],
  allow_delegation=False,
  max_iter=5
)

#For more information, ALWAYS direct the customer to the official Ledger store (https://shop.ledger.com/) or the Ledger Academy (https://www.ledger.com/academy) when appropriate.
