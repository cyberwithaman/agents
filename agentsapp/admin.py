from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    LLMModel, Tool, AgentType, UserProfile, UserPreference, 
    Conversation, Message, AgentConfig, Database
)

# Define an action for bulk deleting users
def bulk_delete_users(modeladmin, request, queryset):
    """Bulk delete users, but prevent deleting superusers"""
    # Filter out superusers
    regular_users = queryset.filter(is_superuser=False)
    deleted_count = regular_users.count()
    
    # Delete the regular users
    regular_users.delete()
    
    modeladmin.message_user(
        request, 
        f"{deleted_count} users deleted successfully. Superusers were preserved."
    )
bulk_delete_users.short_description = "Delete selected users (except superusers)"

# Customize the User admin
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    actions = [bulk_delete_users]

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(LLMModel)
class LLMModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'temperature', 'is_active')
    list_filter = ('provider', 'is_active')
    search_fields = ('name',)


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ('name', 'function_name')
    search_fields = ('name', 'description', 'function_name')


@admin.register(AgentType)
class AgentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'customer_id')
    search_fields = ('user__username', 'customer_id')


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ('profile', 'preference_type', 'value')
    list_filter = ('preference_type',)
    search_fields = ('profile__user__username', 'value')


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'thread_id', 'created_at', 'updated_at', 'agent_info')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('title', 'user__username', 'thread_id')
    inlines = [MessageInline]
    
    def agent_info(self, obj):
        """Display agent information from metadata"""
        if not hasattr(obj, 'metadata'):
            return "No metadata"
            
        metadata = obj.metadata
        if not metadata or 'agent_history' not in metadata:
            return "No agent data"
            
        # Count agent usage
        agent_counts = {}
        for entry in metadata['agent_history']:
            agent_type = entry.get('agent_type', 'unknown')
            agent_counts[agent_type] = agent_counts.get(agent_type, 0) + 1
            
        # Format as string
        return ", ".join([f"{a}: {c}" for a, c in agent_counts.items()])
    
    agent_info.short_description = 'Agent Usage'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'role', 'content_preview', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('content', 'conversation__thread_id')
    
    def content_preview(self, obj):
        return obj.content[:50] + ('...' if len(obj.content) > 50 else '')
    content_preview.short_description = 'Content'


@admin.register(AgentConfig)
class AgentConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'agent_type', 'llm_model', 'is_active')
    list_filter = ('is_active', 'agent_type')
    search_fields = ('name',)
    filter_horizontal = ('tools',)


@admin.register(Database)
class DatabaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
