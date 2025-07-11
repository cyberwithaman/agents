from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    LLMModel, Tool, AgentType, UserProfile, UserPreference, 
    Conversation, Message, AgentConfig, Database
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class LLMModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = LLMModel
        fields = '__all__'


class ToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tool
        fields = '__all__'


class AgentTypeSerializer(serializers.ModelSerializer):
    tools = ToolSerializer(many=True, read_only=True)
    
    class Meta:
        model = AgentType
        fields = '__all__'


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = ['id', 'preference_type', 'value']


class UserProfileSerializer(serializers.ModelSerializer):
    preferences = UserPreferenceSerializer(many=True, read_only=True)
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'customer_id', 'preferences']


class MessageSerializer(serializers.ModelSerializer):
    agent_type = serializers.SerializerMethodField()
    
    class Meta:
        model = Message
        fields = ['id', 'role', 'content', 'tool_call_id', 'name', 'created_at', 'agent_type']
    
    def get_agent_type(self, obj):
        """Get the agent type that generated this message"""
        try:
            if obj.conversation and hasattr(obj.conversation, 'metadata'):
                metadata = obj.conversation.metadata
                if metadata and 'agent_history' in metadata:
                    # Find the agent entry with the closest timestamp to this message
                    agent_entries = metadata['agent_history']
                    for entry in agent_entries:
                        if 'message_id' in entry and entry['message_id'] == obj.id:
                            return entry.get('agent_type', 'unknown')
            return "unknown"
        except Exception:
            return "unknown"


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    user = UserSerializer(read_only=True)
    agents_used = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = ['id', 'thread_id', 'title', 'user', 'messages', 'created_at', 'updated_at', 'agents_used']
    
    def get_agents_used(self, obj):
        """Get a list of unique agents used in this conversation"""
        if hasattr(obj, 'metadata'):
            metadata = obj.metadata
            if metadata and 'agent_history' in metadata:
                return list(set([entry.get('agent_type', 'unknown') 
                           for entry in metadata['agent_history']]))
        return []


class ConversationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for conversation lists"""
    message_count = serializers.SerializerMethodField()
    agent_summary = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = ['id', 'thread_id', 'title', 'created_at', 'updated_at', 'message_count', 'agent_summary', 'last_message']
    
    def get_message_count(self, obj):
        return obj.messages.count()
    
    def get_agent_summary(self, obj):
        """Get a summary of agents used in this conversation"""
        if hasattr(obj, 'metadata'):
            metadata = obj.metadata
            if metadata and 'agent_history' in metadata:
                agent_counts = {}
                for entry in metadata['agent_history']:
                    agent_type = entry.get('agent_type', 'unknown')
                    agent_counts[agent_type] = agent_counts.get(agent_type, 0) + 1
                return agent_counts
        return {}
    
    def get_last_message(self, obj):
        """Get the last message in the conversation"""
        last_message = obj.messages.last()
        if last_message:
            return {
                'role': last_message.role,
                'content': last_message.content[:100] + ('...' if len(last_message.content) > 100 else ''),
                'created_at': last_message.created_at
            }
        return None


class AgentConfigSerializer(serializers.ModelSerializer):
    llm_model = LLMModelSerializer(read_only=True)
    
    class Meta:
        model = AgentConfig
        fields = '__all__'


class DatabaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Database
        fields = '__all__'


class ChatInputSerializer(serializers.Serializer):
    """Serializer for chat input"""
    message = serializers.CharField(required=True)
    thread_id = serializers.CharField(required=False, allow_blank=True)
    user_id = serializers.CharField(required=False, allow_blank=True)


class ChatResponseSerializer(serializers.Serializer):
    """Serializer for chat response"""
    status = serializers.CharField()
    thread_id = serializers.CharField()
    message = serializers.CharField(required=False)
    response = serializers.CharField(required=False)
    requires_input = serializers.BooleanField(required=False, default=False) 
    agent_type = serializers.CharField(required=False)


class ContinueChatSerializer(serializers.Serializer):
    """Serializer for continuing an existing conversation"""
    message = serializers.CharField(required=True)
    continue_from_message_id = serializers.IntegerField(required=False) 