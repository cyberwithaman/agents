import uuid
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.models import User
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone

from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action

from langchain_core.messages import AIMessage

from .models import (
    LLMModel, Tool, AgentType, UserProfile, UserPreference, 
    Conversation, Message, AgentConfig, Database
)
from .serializers import (
    UserSerializer, LLMModelSerializer, ToolSerializer, AgentTypeSerializer,
    UserProfileSerializer, UserPreferenceSerializer, ConversationSerializer,
    ConversationListSerializer, MessageSerializer, AgentConfigSerializer,
    DatabaseSerializer, ChatInputSerializer, ChatResponseSerializer,
    ContinueChatSerializer
)
from .agent_builder import (
    build_complete_agent_system, run_agent_with_input
)
from .utils import save_detailed_chat_history


# Cache for the agent system
_AGENT_SYSTEM = None

def get_agent_system():
    """Get or create the agent system"""
    global _AGENT_SYSTEM
    if _AGENT_SYSTEM is None:
        _AGENT_SYSTEM = build_complete_agent_system()
    return _AGENT_SYSTEM


class UserViewSet(viewsets.ModelViewSet):
    """API endpoint for users"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get the current user"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """Delete multiple users at once"""
        user_ids = request.data.get('user_ids', [])
        
        # Prevent deleting the current user
        if request.user.id in user_ids:
            user_ids.remove(request.user.id)
        
        # Prevent deleting superusers (optional security measure)
        superuser_ids = list(User.objects.filter(
            id__in=user_ids, 
            is_superuser=True
        ).values_list('id', flat=True))
        
        for superuser_id in superuser_ids:
            user_ids.remove(superuser_id)
        
        # Delete the users
        deleted_count = 0
        if user_ids:
            deleted_count = User.objects.filter(id__in=user_ids).delete()[0]
        
        return Response({
            'status': 'success',
            'deleted_count': deleted_count,
            'message': f'{deleted_count} users deleted successfully'
        })


class LLMModelViewSet(viewsets.ModelViewSet):
    """API endpoint for LLM models"""
    queryset = LLMModel.objects.all()
    serializer_class = LLMModelSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['post'])
    def set_active(self, request, pk=None):
        """Set this model as active and deactivate others"""
        model = self.get_object()
        LLMModel.objects.all().update(is_active=False)
        model.is_active = True
        model.save()
        return Response({'status': 'model activated'})


class ToolViewSet(viewsets.ModelViewSet):
    """API endpoint for tools"""
    queryset = Tool.objects.all()
    serializer_class = ToolSerializer
    permission_classes = [permissions.IsAuthenticated]


class AgentTypeViewSet(viewsets.ModelViewSet):
    """API endpoint for agent types"""
    queryset = AgentType.objects.all()
    serializer_class = AgentTypeSerializer
    permission_classes = [permissions.IsAuthenticated]


class UserProfileViewSet(viewsets.ModelViewSet):
    """API endpoint for user profiles"""
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]


class ConversationViewSet(viewsets.ModelViewSet):
    """API endpoint for conversations"""
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'thread_id'
    
    def get_queryset(self):
        """Filter conversations by user"""
        user = self.request.user
        return Conversation.objects.filter(user=user)
    
    def list(self, request):
        """Use lightweight serializer for list view"""
        queryset = self.get_queryset().order_by('-updated_at')
        serializer = ConversationListSerializer(queryset, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, thread_id=None):
        """Get a single conversation by thread_id"""
        conversation = get_object_or_404(self.get_queryset(), thread_id=thread_id)
        serializer = self.get_serializer(conversation)
        return Response(serializer.data)
    
    def create(self, request):
        """Create a new conversation"""
        thread_id = str(uuid.uuid4())
        conversation = Conversation.objects.create(
            user=request.user,
            thread_id=thread_id,
            title=request.data.get('title', 'New Conversation')
        )
        serializer = ConversationListSerializer(conversation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, thread_id=None):
        """Update a conversation"""
        conversation = get_object_or_404(self.get_queryset(), thread_id=thread_id)
        
        # Only title can be updated
        if 'title' in request.data:
            conversation.title = request.data['title']
            conversation.save()
            
        serializer = ConversationListSerializer(conversation)
        return Response(serializer.data)
        
    def destroy(self, request, thread_id=None):
        """Delete a conversation"""
        conversation = get_object_or_404(self.get_queryset(), thread_id=thread_id)
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def continue_from_message(self, request, thread_id=None):
        """Continue a conversation from a specific message"""
        serializer = ContinueChatSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        conversation = get_object_or_404(self.get_queryset(), thread_id=thread_id)
        message_id = serializer.validated_data.get('continue_from_message_id')
        user_input = serializer.validated_data['message']
        
        # Get all messages up to the specified message
        if message_id:
            # Get the message to continue from
            try:
                continue_from = Message.objects.get(id=message_id, conversation=conversation)
                # Delete all messages after this one
                Message.objects.filter(
                    conversation=conversation,
                    created_at__gt=continue_from.created_at
                ).delete()
            except Message.DoesNotExist:
                pass  # If message doesn't exist, just add to the end
        
        # Add new user message
        user_message = Message.objects.create(
            conversation=conversation,
            role='user',
            content=user_input
        )
        
        # Process with the agent
        agent_system = get_agent_system()
        try:
            result = run_agent_with_input(
                agent_system,
                user_input,
                thread_id=conversation.thread_id,
                user_id=str(request.user.id)
            )
            
            # Process the result
            if result['status'] == 'complete':
                # Extract final assistant message
                final_messages = result['result']['messages']
                final_message = None
                
                # Look for the last AI message
                for msg in reversed(final_messages):
                    if hasattr(msg, 'type') and msg.type == 'ai':
                        final_message = msg
                        break
                    elif isinstance(msg, dict) and msg.get('type') == 'ai':
                        final_message = msg
                        break
                    elif hasattr(msg, 'role') and msg.role == 'assistant':
                        final_message = msg
                        break
                    elif isinstance(msg, AIMessage):
                        final_message = msg
                        break
                
                if final_message:
                    # Get content
                    content = ""
                    if hasattr(final_message, 'content'):
                        content = final_message.content
                    elif isinstance(final_message, dict) and 'content' in final_message:
                        content = final_message['content']
                    
                    # Determine agent type
                    agent_type = "unknown_agent"
                    if "music" in user_input.lower() or "song" in user_input.lower():
                        agent_type = "music_catalog_subagent"
                    elif "invoice" in user_input.lower():
                        agent_type = "invoice_information_subagent"
                    else:
                        agent_type = "supervisor_agent"
                    
                    # Save assistant message
                    assistant_message = Message.objects.create(
                        conversation=conversation,
                        role='assistant',
                        content=content
                    )
                    
                    # Save detailed chat history with agent info
                    save_detailed_chat_history(
                        conversation, 
                        content, 
                        agent_type,
                        assistant_message.id
                    )
                    
                    # Update conversation timestamp
                    conversation.updated_at = timezone.now()
                    conversation.save()
                    
                    # Return updated conversation
                    serializer = self.get_serializer(conversation)
                    return Response(serializer.data)
            
            # Handle error or interrupted status
            return Response({
                'status': result['status'],
                'message': result.get('message', 'Error processing request')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['delete'])
    def clear_history(self, request, thread_id=None):
        """Clear conversation history but keep the conversation"""
        conversation = get_object_or_404(self.get_queryset(), thread_id=thread_id)
        Message.objects.filter(conversation=conversation).delete()
        
        # Reset metadata
        conversation.metadata = {'agent_history': []}
        conversation.save()
        
        return Response({'status': 'history cleared'})


class AgentConfigViewSet(viewsets.ModelViewSet):
    """API endpoint for agent configurations"""
    queryset = AgentConfig.objects.all()
    serializer_class = AgentConfigSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['post'])
    def set_active(self, request, pk=None):
        """Set this config as active and deactivate others"""
        config = self.get_object()
        AgentConfig.objects.all().update(is_active=False)
        config.is_active = True
        config.save()
        return Response({'status': 'config activated'})


class DatabaseViewSet(viewsets.ModelViewSet):
    """API endpoint for database configurations"""
    queryset = Database.objects.all()
    serializer_class = DatabaseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['post'])
    def set_active(self, request, pk=None):
        """Set this database as active and deactivate others"""
        db = self.get_object()
        Database.objects.all().update(is_active=False)
        db.is_active = True
        db.save()
        return Response({'status': 'database activated'})


@method_decorator(csrf_exempt, name='dispatch')
class ChatView(APIView):
    """API endpoint for chat interactions"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Process a chat message"""
        serializer = ChatInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Extract data from request
        message = serializer.validated_data['message']
        thread_id = serializer.validated_data.get('thread_id', '')
        user_id = str(request.user.id)
        
        # Get or create conversation
        if thread_id:
            conversation = get_object_or_404(
                Conversation, thread_id=thread_id, user=request.user
            )
        else:
            conversation = Conversation.objects.create(
                user=request.user,
                thread_id=str(uuid.uuid4()),
                title=message[:50]  # Use first 50 chars as title
            )
            thread_id = conversation.thread_id
        
        # Save user message
        user_message = Message.objects.create(
            conversation=conversation,
            role='user',
            content=message
        )
        
        # Get agent system
        agent_system = get_agent_system()
        
        try:
            # Process message with agent
            result = run_agent_with_input(
                agent_system, 
                message, 
                thread_id=thread_id,
                user_id=user_id
            )
            
            # Check if interrupted (needs user input)
            if result['status'] == 'interrupted':
                # Save system message requesting input
                assistant_message = Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=result['message']
                )
                
                # Save detailed chat history with agent info
                save_detailed_chat_history(
                    conversation, 
                    result['message'], 
                    "supervisor_agent",
                    assistant_message.id
                )
                
                return Response({
                    'status': 'interrupted',
                    'thread_id': thread_id,
                    'message': result['message'],
                    'requires_input': True
                })
            
            # Check for error
            elif result['status'] == 'error':
                error_message = f"Error processing message: {result['message']}"
                if 'error_details' in result:
                    print(f"Detailed error: {result['error_details']}")
                
                # Save error message
                assistant_message = Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content="I'm sorry, I encountered an error processing your request. Let me try a different approach."
                )
                
                # Save detailed chat history with agent info
                save_detailed_chat_history(
                    conversation, 
                    "Error processing request", 
                    "error_handler",
                    assistant_message.id
                )
                
                # Try a simplified approach - just use a default response
                assistant_message2 = Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content="I'm having trouble with our AI system at the moment. Please try again later or contact customer support for immediate assistance."
                )
                
                # Save detailed chat history
                save_detailed_chat_history(
                    conversation, 
                    assistant_message2.content, 
                    "fallback_handler",
                    assistant_message2.id
                )
                
                return Response({
                    'status': 'error',
                    'thread_id': thread_id,
                    'message': error_message,
                    'response': "I'm having trouble with our AI system at the moment. Please try again later or contact customer support for immediate assistance."
                })
            
            # Process successful response
            else:
                # Extract final assistant message
                final_messages = result['result']['messages']
                final_message = None
                
                # Look for the last AI message in the list
                for msg in reversed(final_messages):
                    # Check for different message type formats
                    if hasattr(msg, 'type') and msg.type == 'ai':
                        final_message = msg
                        break
                    elif isinstance(msg, dict) and msg.get('type') == 'ai':
                        final_message = msg
                        break
                    elif hasattr(msg, 'role') and msg.role == 'assistant':
                        final_message = msg
                        break
                    elif isinstance(msg, AIMessage):
                        final_message = msg
                        break
                
                if final_message:
                    # Get content based on message format
                    content = ""
                    if hasattr(final_message, 'content'):
                        content = final_message.content
                    elif isinstance(final_message, dict) and 'content' in final_message:
                        content = final_message['content']
                    
                    # Determine which agent handled the request
                    agent_type = "unknown_agent"
                    if "music" in message.lower() or "song" in message.lower() or "artist" in message.lower():
                        agent_type = "music_catalog_subagent"
                    elif "invoice" in message.lower() or "purchase" in message.lower():
                        agent_type = "invoice_information_subagent"
                    else:
                        agent_type = "supervisor_agent"
                    
                    # Save assistant message
                    assistant_message = Message.objects.create(
                        conversation=conversation,
                        role='assistant',
                        content=content
                    )
                    
                    # Save detailed chat history with agent info
                    save_detailed_chat_history(
                        conversation, 
                        content, 
                        agent_type,
                        assistant_message.id
                    )
                    
                    return Response({
                        'status': 'complete',
                        'thread_id': thread_id,
                        'response': content,
                        'agent_type': agent_type
                    })
                else:
                    # No assistant message found, provide a fallback
                    fallback_message = "I processed your request but couldn't generate a proper response. Please try again."
                    
                    # Save fallback message
                    assistant_message = Message.objects.create(
                        conversation=conversation,
                        role='assistant',
                        content=fallback_message
                    )
                    
                    # Save detailed chat history
                    save_detailed_chat_history(
                        conversation, 
                        fallback_message, 
                        "fallback_handler",
                        assistant_message.id
                    )
                    
                    return Response({
                        'status': 'complete',
                        'thread_id': thread_id,
                        'response': fallback_message,
                        'agent_type': 'fallback_handler'
                    })
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in ChatView: {error_details}")
            
            # Save error message
            assistant_message = Message.objects.create(
                conversation=conversation,
                role='assistant',
                content="I'm sorry, I encountered an unexpected error. Please try again."
            )
            
            # Save detailed chat history
            save_detailed_chat_history(
                conversation,
                assistant_message.content,
                "error_handler",
                assistant_message.id
            )
            
            return Response({
                'status': 'error',
                'thread_id': thread_id,
                'message': f"Error processing message: {str(e)}",
                'response': "I'm sorry, I encountered an unexpected error. Please try again."
            })


@method_decorator(csrf_exempt, name='dispatch')
class ChatResumeView(APIView):
    """API endpoint for resuming interrupted chats"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, thread_id):
        """Resume a chat after an interrupt"""
        # Validate input
        if 'message' not in request.data:
            return Response(
                {'error': 'message is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get conversation
        conversation = get_object_or_404(
            Conversation, thread_id=thread_id, user=request.user
        )
        
        # Extract data
        message = request.data['message']
        user_id = str(request.user.id)
        
        # Save user message
        Message.objects.create(
            conversation=conversation,
            role='user',
            content=message
        )
        
        # Get agent system
        agent_system = get_agent_system()
        
        try:
            # Resume with user input
            result = run_agent_with_input(
                agent_system,
                None,  # No initial message when resuming
                thread_id=thread_id,
                user_id=user_id,
                resume_input=message
            )
            
            # Check if interrupted again (needs more user input)
            if result['status'] == 'interrupted':
                # Save system message requesting input
                Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=result['message']
                )
                
                return Response({
                    'status': 'interrupted',
                    'thread_id': thread_id,
                    'message': result['message'],
                    'requires_input': True
                })
            
            # Check for error
            elif result['status'] == 'error':
                error_message = f"Error processing message: {result['message']}"
                if 'error_details' in result:
                    print(f"Detailed error: {result['error_details']}")
                
                # Save error message
                Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content="I'm sorry, I encountered an error processing your request. Let me try again."
                )
                
                # Try again with a fresh conversation
                fresh_result = run_agent_with_input(
                    agent_system,
                    message,  # Use the message as a fresh input
                    thread_id=thread_id,
                    user_id=user_id
                )
                
                # Process the fresh result
                if fresh_result['status'] == 'complete':
                    # Extract final assistant message
                    final_messages = fresh_result['result']['messages']
                    final_message = None
                    
                    # Look for the last AI message in the list
                    for msg in reversed(final_messages):
                        # Check for different message type formats
                        if hasattr(msg, 'type') and msg.type == 'ai':
                            final_message = msg
                            break
                        elif isinstance(msg, dict) and msg.get('type') == 'ai':
                            final_message = msg
                            break
                        elif hasattr(msg, 'role') and msg.role == 'assistant':
                            final_message = msg
                            break
                        elif isinstance(msg, AIMessage):
                            final_message = msg
                            break
                    
                    if final_message:
                        # Get content based on message format
                        content = ""
                        if hasattr(final_message, 'content'):
                            content = final_message.content
                        elif isinstance(final_message, dict) and 'content' in final_message:
                            content = final_message['content']
                        
                        # Save assistant message
                        Message.objects.create(
                            conversation=conversation,
                            role='assistant',
                            content=content
                        )
                        
                        return Response({
                            'status': 'complete',
                            'thread_id': thread_id,
                            'response': content
                        })
                
                # If fresh attempt also failed, return error
                return Response({
                    'status': 'error',
                    'thread_id': thread_id,
                    'message': error_message
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Process successful response
            else:
                # Extract final assistant message
                final_messages = result['result']['messages']
                final_message = None
                
                # Look for the last AI message in the list
                for msg in reversed(final_messages):
                    # Check for different message type formats
                    if hasattr(msg, 'type') and msg.type == 'ai':
                        final_message = msg
                        break
                    elif isinstance(msg, dict) and msg.get('type') == 'ai':
                        final_message = msg
                        break
                    elif hasattr(msg, 'role') and msg.role == 'assistant':
                        final_message = msg
                        break
                    elif isinstance(msg, AIMessage):
                        final_message = msg
                        break
                
                if final_message:
                    # Get content based on message format
                    content = ""
                    if hasattr(final_message, 'content'):
                        content = final_message.content
                    elif isinstance(final_message, dict) and 'content' in final_message:
                        content = final_message['content']
                    
                    # Save assistant message
                    Message.objects.create(
                        conversation=conversation,
                        role='assistant',
                        content=content
                    )
                    
                    return Response({
                        'status': 'complete',
                        'thread_id': thread_id,
                        'response': content
                    })
                else:
                    return Response({
                        'status': 'error',
                        'thread_id': thread_id,
                        'message': "No assistant response found"
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in ChatResumeView: {error_details}")
            
            # Save error message
            Message.objects.create(
                conversation=conversation,
                role='assistant',
                content="I'm sorry, I encountered an unexpected error. Let's start fresh."
            )
            
            return Response({
                'status': 'error',
                'thread_id': thread_id,
                'message': f"Error processing message: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def system_info(request):
    """Get system information"""
    import platform
    import psutil
    
    # Get system info
    system_info = {
        'os': platform.system(),
        'os_version': platform.version(),
        'architecture': platform.machine(),
        'processor': platform.processor(),
        'cpu_count': psutil.cpu_count(),
        'memory_total': psutil.virtual_memory().total,
        'memory_available': psutil.virtual_memory().available,
    }
    
    # Get LLM info
    active_model = LLMModel.objects.filter(is_active=True).first()
    if active_model:
        llm_info = {
            'name': active_model.name,
            'provider': active_model.provider,
            'temperature': active_model.temperature
        }
    else:
        llm_info = {
            'name': 'Default Ollama',
            'provider': 'ollama',
            'temperature': 0.0
        }
    
    return Response({
        'system': system_info,
        'llm': llm_info
    })


def login_view(request):
    """Login view"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('index')
        else:
            messages.error(request, 'Invalid username or password')
    
    return render(request, 'agentsapp/login.html')

def logout_view(request):
    """Logout view"""
    logout(request)
    return redirect('login')

@login_required
def index(request):
    """Render the main chat interface"""
    return render(request, 'agentsapp/index.html')
