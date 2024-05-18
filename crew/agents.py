
from crewai import Agent
from crew.tool import retriever_tool
from langchain_openai import ChatOpenAI
from langchain.agents import load_tools

gpt_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.0
)

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
  llm=gpt_llm,
  max_iter=5
)

#For more information, ALWAYS direct the customer to the official Ledger store (https://shop.ledger.com/) or the Ledger Academy (https://www.ledger.com/academy) when appropriate.
