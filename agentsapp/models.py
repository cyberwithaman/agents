from django.db import models
from django.contrib.auth.models import User
import uuid
import json
from django.utils import timezone


class LLMModel(models.Model):
    """Model for storing LLM configurations"""
    name = models.CharField(max_length=100)
    provider = models.CharField(max_length=50)
    api_base = models.CharField(max_length=200, blank=True, null=True)
    api_key = models.CharField(max_length=200, blank=True, null=True)
    model_path = models.CharField(max_length=500, blank=True, null=True)
    temperature = models.FloatField(default=0.7)
    max_tokens = models.IntegerField(default=1000)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.name} ({self.provider})"


class AgentType(models.Model):
    """Model for storing agent type configurations"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name


class Tool(models.Model):
    """Model for storing tool configurations"""
    name = models.CharField(max_length=100)
    description = models.TextField()
    function_name = models.CharField(max_length=100)
    
    def __str__(self):
        return self.name


class AgentConfig(models.Model):
    """Model for storing agent configurations"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    agent_type = models.ForeignKey(AgentType, on_delete=models.CASCADE, null=True, blank=True)
    llm_model = models.ForeignKey(LLMModel, on_delete=models.CASCADE, null=True, blank=True)
    system_prompt = models.TextField(blank=True, null=True, default="")
    tools = models.ManyToManyField(Tool, blank=True)
    is_active = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.name} ({self.agent_type.name if self.agent_type else 'No Type'})"


class Database(models.Model):
    """Model for storing database configurations"""
    name = models.CharField(max_length=100)
    connection_string = models.CharField(max_length=500)
    is_active = models.BooleanField(default=False)
    
    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Model for storing user profiles"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    customer_id = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"Profile for {self.user.username}"


class UserPreference(models.Model):
    """Model for storing user preferences"""
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="preferences")
    preference_type = models.CharField(max_length=50)  # e.g., "music", "payment"
    value = models.CharField(max_length=100)  # e.g., "rock", "jazz", "credit card"
    
    class Meta:
        unique_together = ["profile", "preference_type", "value"]
    
    def __str__(self):
        return f"{self.profile.user.username} - {self.preference_type}: {self.value}"


class Conversation(models.Model):
    """Model for storing conversations"""
    thread_id = models.UUIDField(default=uuid.uuid4, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    _metadata = models.TextField(blank=True, null=True, db_column="metadata")
    
    def __str__(self):
        return f"{self.title} ({self.user.username})"
    
    @property
    def metadata(self):
        """Get metadata as dictionary"""
        if self._metadata:
            return json.loads(self._metadata)
        return {}
    
    @metadata.setter
    def metadata(self, value):
        """Set metadata from dictionary"""
        self._metadata = json.dumps(value)


class Message(models.Model):
    """Model for storing messages"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=50)  # user, assistant, system, tool
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Tool message fields
    tool_call_id = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        ordering = ["created_at"]
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
