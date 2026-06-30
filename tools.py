from langchain.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os 
from rich import print
from dotenv import load_dotenv
load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@tool 
def web_search(query : str) -> str:
    """
    Search the web for recent and reliable information on a topic 
    Returns Titles , URLs and snippets
    """
    try:
        results = tavily.search(query=query,max_results=5)
        response = ""
        for result in results["results"]:
            response += f"Title : {result['title']}\n"
            response += f"URL : {result['url']}\n"
            response += f"Snippet : {result['content']}\n\n"
        return response
    except Exception as e:
        return f"Error : {e}"

# print(web_search.invoke("What are the recent news of Ai"))

@tool 
def scrape_url(url : str) -> str:
    """
    Scrapes and return clean text content from a given URL for deeper reading.
    """
    try:
        resp = requests.get(url,timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text,'html.parser')
        # clean the text 
        for script in soup(['script','style','header','footer','nav']):
            script.decompose()
        return soup.get_text(separator=" ", strip = True)[:3000]
    except Exception as e:
        return f"Error : {str(e)}"