from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router for REST API viewsets
router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'llm-models', views.LLMModelViewSet)
router.register(r'tools', views.ToolViewSet)
router.register(r'agent-types', views.AgentTypeViewSet)
router.register(r'profiles', views.UserProfileViewSet)
router.register(r'conversations', views.ConversationViewSet, basename='conversation')
router.register(r'agent-configs', views.AgentConfigViewSet)
router.register(r'databases', views.DatabaseViewSet)

urlpatterns = [
    # Authentication routes
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # REST API routes
    path('api/', include(router.urls)),
    path('api/chat/', views.ChatView.as_view(), name='chat'),
    path('api/chat/<str:thread_id>/resume/', views.ChatResumeView.as_view(), name='chat-resume'),
    path('api/system-info/', views.system_info, name='system-info'),
    
    # Main app route
    path('', views.index, name='index'),
] 