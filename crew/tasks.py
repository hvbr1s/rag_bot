from crewai import Task
from crew.agents import researcher

# Research task
search_docs= Task(
  description=(
    """
    Use your Knowledge base tool to find the best answer to: '{topic}'.
    ALWAYS use your Knowledge Base tool to answer the question asked: '{topic}'.
    After using your tool, assess if the information retrieved can correctly answer this question: '{topic}'. 
    If it does not answer the question, use your tool again until you find the answer.
    You're allowed to discard any retrieved information that does not directly answer the question.
    Make sure to always cite your sources by adding a plain URL link next to the title of the article. For example: "Learn more by reading the article title <title> whihc you can find at <plain url>
    
    """
  ),
  expected_output="A detailed summary of the solution and the plain URL link or links (no markdown) to the relevant documentation that answers: '{topic}'",
  agent=researcher,
  async_execution=False,

)
