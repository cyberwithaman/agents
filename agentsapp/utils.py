import os
import uuid
import json
import sqlite3
from typing import Dict, List, Optional, Any, TypedDict, Annotated
from typing_extensions import TypedDict
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

from langchain_community.llms import Ollama, GPT4All
# Replace deprecated ChatOllama import
from langchain_ollama import ChatOllama
from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, ToolMessage, AnyMessage
)
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.utilities.sql_database import SQLDatabase

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore
from langgraph.prebuilt import create_react_agent, ToolNode
from langgraph.graph.message import add_messages
from langgraph.managed.is_last_step import RemainingSteps
from langgraph.types import interrupt

from .models import LLMModel, AgentConfig, Database, Conversation, Message, UserProfile, UserPreference
from django.utils import timezone


# Define the State class for the LangGraph
class State(TypedDict):
    """Represents the state of our LangGraph agent."""
    customer_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    loaded_memory: str
    remaining_steps: RemainingSteps


def create_supervisor(
    llm,
    tools,
    name="supervisor",
    system_prompt=None,
    state_schema=None,
    checkpointer=None,
    store=None,
):
    """
    Create a supervisor agent that can route to other agents.
    
    Args:
        llm: The language model to use
        tools: List of tools (including agent tools)
        name: Name of the supervisor agent
        system_prompt: System prompt for the supervisor
        state_schema: Schema for the graph state
        checkpointer: Checkpointer for persistence
        store: Store for long-term memory
        
    Returns:
        A compiled StateGraph for the supervisor
    """
    # Default system prompt if none provided
    if system_prompt is None:
        system_prompt = """You are a supervisor agent that routes queries to specialized agents.
        You have access to the following agents:
        {tool_descriptions}
        
        Route the query to the most appropriate agent based on the content.
        """
    
    # Format the system prompt with tool descriptions
    tool_descriptions = "\n".join([f"- {tool.name}: {tool.description}" for tool in tools])
    formatted_prompt = system_prompt.format(tool_descriptions=tool_descriptions)
    
    # Define the supervisor node function
    def supervisor_node(state, config):
        try:
            # Get user input from state
            if "messages" in state and state["messages"]:
                user_input = state["messages"][-1].content
            else:
                user_input = "Hello"
                
            # Create a simple direct response without using the LLM for tool selection
            # This avoids the 404 error when trying to access Ollama
            print(f"Processing user input in supervisor: {user_input[:50]}...")
            
            # Simple keyword-based routing
            if any(music_term in user_input.lower() for music_term in ["music", "song", "artist", "album", "track", "genre"]):
                selected_tool = next((tool for tool in tools if "music" in tool.name.lower()), None)
            elif any(invoice_term in user_input.lower() for invoice_term in ["invoice", "purchase", "buy", "order", "payment"]):
                selected_tool = next((tool for tool in tools if "invoice" in tool.name.lower()), None)
            else:
                # Default to first tool
                selected_tool = tools[0] if tools else None
            
            # Execute the selected tool if found
            if selected_tool:
                try:
                    print(f"Using tool: {selected_tool.name}")
                    tool_result = selected_tool.func({"messages": state["messages"]})
                    
                    # Extract the response from the tool result
                    if isinstance(tool_result, dict) and "messages" in tool_result:
                        for msg in reversed(tool_result["messages"]):
                            if hasattr(msg, 'content'):
                                response = msg.content
                                break
                        else:
                            response = f"The {selected_tool.name} processed your request but didn't provide a specific answer."
                    else:
                        response = str(tool_result)
                    
                    # Return the response
                    return {"messages": [AIMessage(content=response)]}
                except Exception as tool_error:
                    print(f"Error executing tool {selected_tool.name}: {str(tool_error)}")
                    # Fall through to direct response
            
            # Direct response if tool execution failed or no tool was found
            return {"messages": [AIMessage(content="I'm sorry, I couldn't process your request through our specialized agents. Is there anything specific about our music catalog or your invoices that you'd like to know?")]}
            
        except Exception as e:
            print(f"Error in supervisor_node: {str(e)}")
            return {"messages": [AIMessage(content="I'm sorry, I'm having trouble processing your request right now. Please try again later.")]}
    
    # Create the graph
    supervisor_graph = StateGraph(state_schema or State)
    supervisor_graph.add_node("supervisor", supervisor_node)
    supervisor_graph.add_edge(START, "supervisor")
    supervisor_graph.add_edge("supervisor", END)
    
    # Compile the graph
    return supervisor_graph.compile(
        name=name,
        checkpointer=checkpointer,
        store=store
    )


def get_llm(model_name: Optional[str] = None):
    """
    Get a language model instance based on configuration.
    
    Args:
        model_name: Optional name of the model to use, otherwise uses active model
        
    Returns:
        A language model instance (Ollama, GPT4All, etc.)
    """
    try:
        # Get the active model from database or use specified model
        if model_name:
            try:
                model = LLMModel.objects.get(name=model_name)
            except LLMModel.DoesNotExist:
                # Default to first active model or create basic Ollama config
                model = LLMModel.objects.filter(is_active=True).first()
                if not model:
                    # Use Ollama with default settings if no models configured
                    print("No model found, using default Ollama config")
                    return ChatOllama(model="llama2", temperature=0, base_url="http://localhost:11434")
        else:
            model = LLMModel.objects.filter(is_active=True).first()
            if not model:
                # Use Ollama with default settings if no models configured
                print("No active model found, using default Ollama config")
                return ChatOllama(model="llama2", temperature=0, base_url="http://localhost:11434")
        
        # Initialize the appropriate model based on provider
        if model.provider == 'ollama':
            # Make sure we always have a base_url
            base_url = model.api_base if model.api_base else "http://localhost:11434"
            print(f"Creating Ollama model with base_url: {base_url}")
            return ChatOllama(
                model=model.name,
                temperature=model.temperature,
                base_url=base_url
            )
        elif model.provider == 'gpt4all':
            return GPT4All(
                model=model.model_path,
                temperature=model.temperature,
                max_tokens=model.max_tokens
            )
        elif model.provider == 'llama-cpp':
            # Import here to avoid loading if not used
            from langchain_community.llms import LlamaCpp
            return LlamaCpp(
                model_path=model.model_path,
                temperature=model.temperature,
                max_tokens=model.max_tokens,
                n_ctx=2048,  # Context window
                n_gpu_layers=-1  # Auto-detect GPU layers
            )
        else:
            # Fallback to Ollama
            print(f"Unknown provider {model.provider}, falling back to default Ollama")
            return ChatOllama(model="llama2", temperature=0, base_url="http://localhost:11434")
    except Exception as e:
        # If anything fails, use a safe default
        print(f"Error creating LLM: {str(e)}, using default Ollama config")
        return ChatOllama(model="llama2", temperature=0, base_url="http://localhost:11434")


def get_db_connection(db_name: Optional[str] = None):
    """
    Get a database connection based on configuration.
    
    Args:
        db_name: Optional name of the database to connect to
        
    Returns:
        A SQLDatabase instance
    """
    # Get the active database from Django models or use specified database
    if db_name:
        try:
            db_config = Database.objects.get(name=db_name)
        except Database.DoesNotExist:
            # Default to SQLite in-memory database if not found
            connection = sqlite3.connect(":memory:", check_same_thread=False)
            return SQLDatabase(connection)
    else:
        db_config = Database.objects.filter(is_active=True).first()
        if not db_config:
            # Default to SQLite in-memory database if not configured
            connection = sqlite3.connect(":memory:", check_same_thread=False)
            return SQLDatabase(connection)
    
    # Connect to the configured database
    return SQLDatabase.from_uri(db_config.connection_string)


def get_embeddings():
    """Get embeddings model for vector search"""
    # Use Ollama embeddings for efficient local embedding
    return OllamaEmbeddings(model="nomic-embed-text")


def get_checkpointer():
    """Get a checkpointer for thread-level memory"""
    # Use in-memory checkpointer for now to avoid SQLite issues
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


def get_memory_store():
    """Get a memory store for long-term memory"""
    # Use in-memory store for now to avoid SQLite issues
    from langgraph.store.memory import InMemoryStore
    return InMemoryStore()


def load_user_memory(user_id: str) -> str:
    """
    Load user preferences from database
    
    Args:
        user_id: User ID to load preferences for
        
    Returns:
        Formatted string of user preferences
    """
    try:
        profile = UserProfile.objects.get(user_id=user_id)
        preferences = UserPreference.objects.filter(profile=profile)
        
        if not preferences:
            return "None"
        
        # Format preferences by type
        pref_by_type = {}
        for pref in preferences:
            if pref.preference_type not in pref_by_type:
                pref_by_type[pref.preference_type] = []
            pref_by_type[pref.preference_type].append(pref.value)
        
        # Build formatted string
        result = []
        for pref_type, values in pref_by_type.items():
            result.append(f"{pref_type.title()} Preferences: {', '.join(values)}")
        
        return "\n".join(result)
    except UserProfile.DoesNotExist:
        return "None"


def save_user_memory(user_id: str, customer_id: str, preferences: Dict[str, List[str]]):
    """
    Save user preferences to database
    
    Args:
        user_id: User ID to save preferences for
        customer_id: Customer ID for the user
        preferences: Dictionary of preference types and values
    """
    # Get or create user profile
    profile, _ = UserProfile.objects.get_or_create(
        user_id=user_id,
        defaults={'customer_id': customer_id}
    )
    
    # Update preferences
    for pref_type, values in preferences.items():
        # Delete existing preferences of this type
        UserPreference.objects.filter(
            profile=profile,
            preference_type=pref_type
        ).delete()
        
        # Create new preferences
        for value in values:
            UserPreference.objects.create(
                profile=profile,
                preference_type=pref_type,
                value=value
            )


def save_conversation_message(conversation_id, role, content, **kwargs):
    """
    Save a message to the conversation history
    
    Args:
        conversation_id: Conversation ID
        role: Message role (user, assistant, system, tool)
        content: Message content
        **kwargs: Additional message attributes
    """
    try:
        conversation = Conversation.objects.get(thread_id=conversation_id)
        Message.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            **kwargs
        )
    except Conversation.DoesNotExist:
        pass  # Conversation doesn't exist, can't save message


def get_conversation_messages(conversation_id):
    """
    Get messages from a conversation
    
    Args:
        conversation_id: Conversation ID
        
    Returns:
        List of messages in LangChain format
    """
    try:
        conversation = Conversation.objects.get(thread_id=conversation_id)
        messages = []
        
        for msg in conversation.messages.all():
            if msg.role == 'user':
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == 'assistant':
                messages.append(AIMessage(content=msg.content))
            elif msg.role == 'system':
                messages.append(SystemMessage(content=msg.content))
            elif msg.role == 'tool':
                messages.append(ToolMessage(
                    content=msg.content,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name
                ))
        
        return messages
    except Conversation.DoesNotExist:
        return []


# Music catalog tools
@tool
def get_albums_by_artist(artist: str):
    """Get albums by an artist."""
    db = get_db_connection()
    return db.run(
        f"""
        SELECT Album.Title, Artist.Name 
        FROM Album 
        JOIN Artist ON Album.ArtistId = Artist.ArtistId 
        WHERE Artist.Name LIKE '%{artist}%';
        """,
        include_columns=True
    )


@tool
def get_tracks_by_artist(artist: str):
    """Get songs by an artist (or similar artists)."""
    db = get_db_connection()
    return db.run(
        f"""
        SELECT Track.Name as SongName, Artist.Name as ArtistName 
        FROM Album 
        LEFT JOIN Artist ON Album.ArtistId = Artist.ArtistId 
        LEFT JOIN Track ON Track.AlbumId = Album.AlbumId 
        WHERE Artist.Name LIKE '%{artist}%';
        """,
        include_columns=True
    )


@tool
def get_songs_by_genre(genre: str):
    """Fetch songs from the database that match a specific genre."""
    db = get_db_connection()
    # First, find the GenreId for the given genre name
    genre_id_query = f"SELECT GenreId FROM Genre WHERE Name LIKE '%{genre}%'"
    genre_ids = db.run(genre_id_query)
    
    # If no genre IDs are found, return an informative message
    if not genre_ids:
        return f"No songs found for the genre: {genre}"
    
    # Extract the GenreId values
    import ast
    genre_ids = ast.literal_eval(genre_ids)
    genre_id_list = ", ".join(str(gid[0]) for gid in genre_ids)

    # Get songs for the found genre IDs
    songs_query = f"""
        SELECT Track.Name as SongName, Artist.Name as ArtistName
        FROM Track
        LEFT JOIN Album ON Track.AlbumId = Album.AlbumId
        LEFT JOIN Artist ON Album.ArtistId = Artist.ArtistId
        WHERE Track.GenreId IN ({genre_id_list})
        GROUP BY Artist.Name
        LIMIT 8;
    """
    songs = db.run(songs_query, include_columns=True)
    
    # Format and return the results
    if not songs:
        return f"No songs found for the genre: {genre}"
    
    formatted_songs = ast.literal_eval(songs)
    return [
        {"Song": song["SongName"], "Artist": song["ArtistName"]}
        for song in formatted_songs
    ]


@tool
def check_for_songs(song_title):
    """Check if a song exists by its name."""
    db = get_db_connection()
    return db.run(
        f"""
        SELECT * FROM Track WHERE Name LIKE '%{song_title}%';
        """,
        include_columns=True
    )


# Invoice tools
@tool 
def get_invoices_by_customer_sorted_by_date(customer_id: str):
    """Look up all invoices for a customer using their ID."""
    db = get_db_connection()
    return db.run(
        f"SELECT * FROM Invoice WHERE CustomerId = {customer_id} ORDER BY InvoiceDate DESC;",
        include_columns=True
    )


@tool 
def get_invoices_sorted_by_unit_price(customer_id: str):
    """Look up all invoices for a customer, sorted by unit price."""
    db = get_db_connection()
    query = f"""
        SELECT Invoice.*, InvoiceLine.UnitPrice
        FROM Invoice
        JOIN InvoiceLine ON Invoice.InvoiceId = InvoiceLine.InvoiceId
        WHERE Invoice.CustomerId = {customer_id}
        ORDER BY InvoiceLine.UnitPrice DESC;
    """
    return db.run(query, include_columns=True)


@tool
def get_employee_by_invoice_and_customer(invoice_id: str, customer_id: str):
    """Get employee information associated with an invoice and customer."""
    db = get_db_connection()
    query = f"""
        SELECT Employee.FirstName, Employee.Title, Employee.Email
        FROM Employee
        JOIN Customer ON Customer.SupportRepId = Employee.EmployeeId
        JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId
        WHERE Invoice.InvoiceId = ({invoice_id}) AND Invoice.CustomerId = ({customer_id});
    """
    employee_info = db.run(query, include_columns=True)
    
    if not employee_info:
        return f"No employee found for invoice ID {invoice_id} and customer identifier {customer_id}."
    return employee_info


# Helper for customer verification
def get_customer_id_from_identifier(identifier: str) -> Optional[int]:
    """
    Retrieve Customer ID using an identifier (ID, email, or phone).
    """
    db = get_db_connection()
    
    # Check if identifier is a customer ID
    if identifier.isdigit():
        return int(identifier)
    
    # Check if identifier is a phone number
    elif identifier[0] == "+":
        query = f"SELECT CustomerId FROM Customer WHERE Phone = '{identifier}';"
        result = db.run(query)
        import ast
        formatted_result = ast.literal_eval(result)
        if formatted_result:
            return formatted_result[0][0]
    
    # Check if identifier is an email
    elif "@" in identifier:
        query = f"SELECT CustomerId FROM Customer WHERE Email = '{identifier}';"
        result = db.run(query)
        import ast
        formatted_result = ast.literal_eval(result)
        if formatted_result:
            return formatted_result[0][0]
    
    return None 


def save_detailed_chat_history(conversation, message, agent_type=None, message_id=None):
    """
    Save a detailed chat history with agent information
    
    Args:
        conversation: The conversation object
        message: The message content
        agent_type: The type of agent that generated the response
        message_id: The ID of the message object
    """
    try:
        # If agent type not provided, try to detect it from the message
        if not agent_type:
            if "music" in message.lower() or "song" in message.lower() or "artist" in message.lower():
                agent_type = "music_catalog_subagent"
            elif "invoice" in message.lower() or "purchase" in message.lower():
                agent_type = "invoice_information_subagent"
            else:
                agent_type = "supervisor_agent"
                
        # Add metadata to conversation if it doesn't exist
        if not hasattr(conversation, "metadata") or not conversation.metadata:
            conversation.metadata = {}
            
        # Update metadata with agent info
        if "agent_history" not in conversation.metadata:
            conversation.metadata["agent_history"] = []
            
        # Add this interaction to agent history
        entry = {
            "timestamp": str(timezone.now()),
            "agent_type": agent_type,
            "message_length": len(message)
        }
        
        # Add message ID if provided
        if message_id:
            entry["message_id"] = message_id
            
        conversation.metadata["agent_history"].append(entry)
        
        # Save conversation with updated metadata
        conversation.save()
        
    except Exception as e:
        print(f"Error saving detailed chat history: {str(e)}") 