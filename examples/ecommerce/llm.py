from openai import AsyncAzureOpenAI
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
import os

def get_azure_openai_client():
    """Initialize Azure OpenAI client with DefaultAzureCredential."""

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")

    return AsyncAzureOpenAI(
        azure_endpoint=azure_endpoint,
        azure_deployment=azure_deployment,
        api_key=azure_api_key,
        api_version="2024-12-01-preview"
    )

def get_openai_chat_model():
    """Get OpenAI chat model with Azure OpenAI client."""
    client = get_azure_openai_client()
    return OpenAIChatCompletionsModel(
        openai_client=client,
        model="gpt-35-turbo"
    )