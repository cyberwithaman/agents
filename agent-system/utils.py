import os
from IPython.display import Image, display
from langchain_core.runnables.graph import MermaidDrawMethod
import nest_asyncio
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader
from langchain_chroma import Chroma

# Import local embedding models
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama, GPT4All, LlamaCpp
from langchain_community.chat_models import ChatOllama

# Function to get the LLM based on configuration
def get_llm(provider="ollama", model_name="llama2", temperature=0, 
            model_path=None, max_tokens=512, api_base=None):
    """
    Get a language model instance based on configuration.
    
    Args:
        provider: The provider of the model (ollama, gpt4all, llama-cpp)
        model_name: Name of the model to use
        temperature: Temperature for generation
        model_path: Path to model file (for gpt4all and llama-cpp)
        max_tokens: Maximum tokens for generation
        api_base: Base URL for API (for Ollama)
        
    Returns:
        A language model instance
    """
    if provider == 'ollama':
        kwargs = {"model": model_name, "temperature": temperature}
        if api_base:
            kwargs["base_url"] = api_base
        return ChatOllama(**kwargs)
    elif provider == 'gpt4all':
        return GPT4All(
            model=model_path,
            temperature=temperature,
            max_tokens=max_tokens
        )
    elif provider == 'llama-cpp':
        return LlamaCpp(
            model_path=model_path,
            temperature=temperature,
            max_tokens=max_tokens,
            n_ctx=2048,  # Context window
            n_gpu_layers=-1  # Auto-detect GPU layers
        )
    else:
        # Fallback to Ollama
        return ChatOllama(model=model_name, temperature=temperature)

# Function to get embeddings
def get_embeddings(provider="ollama", model_name="nomic-embed-text"):
    """Get embeddings model for vector search"""
    if provider == "ollama":
        return OllamaEmbeddings(model=model_name)
    else:
        # Default to Ollama embeddings
        return OllamaEmbeddings(model="nomic-embed-text")

# List of URLs containing LangGraph documentation
# These URLs cover tutorials, concepts, and guides for the LangGraph framework
LANGGRAPH_DOCS = [
    "https://langchain-ai.github.io/langgraph/",  # Main documentation page
    "https://langchain-ai.github.io/langgraph/tutorials/customer-support/customer-support/",  # Customer support tutorial
    "https://langchain-ai.github.io/langgraph/tutorials/chatbots/information-gather-prompting/",  # Chatbot tutorial
    "https://langchain-ai.github.io/langgraph/tutorials/code_assistant/langgraph_code_assistant/",  # Code assistant tutorial
    "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/",  # Multi-agent collaboration
    "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/agent_supervisor/",  # Agent supervisor pattern
    "https://langchain-ai.github.io/langgraph/tutorials/multi_agent/hierarchical_agent_teams/",  # Hierarchical agent teams
    "https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/plan-and-execute/",  # Plan and execute pattern
    "https://langchain-ai.github.io/langgraph/tutorials/rewoo/rewoo/",  # ReWOO (Reasoning WithOut Observation) tutorial
    "https://langchain-ai.github.io/langgraph/tutorials/llm-compiler/LLMCompiler/",  # LLM Compiler tutorial
    "https://langchain-ai.github.io/langgraph/concepts/high_level/",  # High-level concepts
    "https://langchain-ai.github.io/langgraph/concepts/low_level/",  # Low-level concepts
    "https://langchain-ai.github.io/langgraph/concepts/agentic_concepts/",  # Agentic concepts
    "https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/",  # Human-in-the-loop concepts
    "https://langchain-ai.github.io/langgraph/concepts/multi_agent/",  # Multi-agent concepts
    "https://langchain-ai.github.io/langgraph/concepts/persistence/",  # Persistence concepts
    "https://langchain-ai.github.io/langgraph/concepts/streaming/",  # Streaming concepts
    "https://langchain-ai.github.io/langgraph/concepts/faq/"  # Frequently asked questions
]

def get_langgraph_docs_retriever(persist_directory="langgraph-docs-db", embedding_model=None):
    """
    Loads or creates a retriever for LangGraph documentation using a persisted Chroma vectorstore.
    
    This function implements a caching mechanism:
    1. If a vectorstore already exists on disk, it loads and returns it
    2. If no vectorstore exists, it downloads the documentation, creates embeddings,
       stores them in a vectorstore, and persists it to disk for future use

    Args:
        persist_directory: Directory to persist the vectorstore
        embedding_model: Embedding model to use (defaults to Ollama if None)
        
    Returns:
        Retriever: A retriever object for querying the LangGraph documentation using similarity search
    """
    # Use provided embedding model or get default
    if embedding_model is None:
        embedding_model = get_embeddings()
        
    # Check if the vectorstore directory already exists on disk
    # This allows us to skip the expensive document loading and embedding process
    if os.path.exists(persist_directory):
        print("Loading vectorstore from disk...")
        # Load the existing vectorstore from the persistent directory
        vectorstore = Chroma(
            collection_name="langgraph-docs",  # Name of the collection in the vectorstore
            embedding_function=embedding_model,  # Embedding model for query encoding
            persist_directory=persist_directory  # Directory where the vectorstore is saved
        )
        # Return a retriever interface for the vectorstore
        # lambda_mult=0 disables the MMR (Maximum Marginal Relevance) diversity filter
        return vectorstore.as_retriever(lambda_mult=0)

    # If vectorstore doesn't exist, create it from scratch
    print("Creating new vectorstore from documentation...")
    
    # Download and load documents from each URL in LANGGRAPH_DOCS
    # WebBaseLoader fetches the content from web pages and converts them to Document objects
    docs = [WebBaseLoader(url).load() for url in LANGGRAPH_DOCS]
    
    # Flatten the list of lists into a single list of documents
    # Each WebBaseLoader.load() returns a list, so we need to flatten the nested structure
    docs_list = [item for sublist in docs for item in sublist]
    
    # Split documents into smaller chunks for better retrieval performance
    # Smaller chunks allow for more precise similarity matching
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=200,  # Maximum tokens per chunk (small chunks for precise retrieval)
        chunk_overlap=0  # No overlap between chunks to avoid redundancy
    )
    doc_splits = text_splitter.split_documents(docs_list)
    
    # Create a new Chroma vectorstore with the specified configuration
    vectorstore = Chroma(
        collection_name="langgraph-docs",  # Name of the collection
        embedding_function=embedding_model,  # Embedding model for converting text to vectors
        persist_directory=persist_directory  # Directory to persist the vectorstore
    )
    
    # Add the split documents to the vectorstore
    # This creates embeddings for each chunk and stores them in the vector database
    vectorstore.add_documents(doc_splits)
    print("Vectorstore created and persisted to disk")
    
    # Return a retriever interface for the new vectorstore
    return vectorstore.as_retriever(lambda_mult=0)

def show_graph(graph, xray=False):
    """
    Display a LangGraph mermaid diagram with fallback rendering.
    
    This function attempts to render a LangGraph as a visual diagram using Mermaid.
    It includes error handling to fall back to an alternative renderer if the default fails.
    
    Args:
        graph: The LangGraph object that has a get_graph() method for visualization
        xray (bool): Whether to show internal graph details in xray mode
        
    Returns:
        Image: An IPython Image object containing the rendered graph diagram
    """
    from IPython.display import Image
    
    try:
        # Try the default mermaid renderer first (uses mermaid.ink service)
        # This is the fastest option but may fail due to network issues or service unavailability
        return Image(graph.get_graph(xray=xray).draw_mermaid_png())
    except Exception as e:
        # If the default renderer fails, fall back to pyppeteer
        # pyppeteer uses a local headless Chrome instance to render the diagram
        print(f"Default renderer failed ({e}), falling back to pyppeteer...")
        
        # Apply nest_asyncio to handle async operations in Jupyter environments
        # This is necessary because pyppeteer uses async operations
        import nest_asyncio
        nest_asyncio.apply()
        
        # Import the MermaidDrawMethod enum for specifying the draw method
        from langchain_core.runnables.graph import MermaidDrawMethod
        
        # Use pyppeteer as the drawing method (local rendering)
        return Image(graph.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.PYPPETEER))