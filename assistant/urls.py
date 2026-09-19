from django.urls import path
from . import views
urlpatterns = [
    path('career-assistant/', views.career_assistant, name='career_assistant'),
    path('', views.home, name='home'), path('health/', views.health, name='health'),
    path('accounts/signup/', views.signup, name='signup'), path('dashboard/', views.dashboard, name='dashboard'),
    path('resumes/', views.resumes, name='resumes'), path('resumes/new/', views.resume_edit, name='resume_create'),
    path('resumes/<int:pk>/edit/', views.resume_edit, name='resume_edit'),
    path('analyses/', views.analyses, name='analyses'), path('analyses/new/', views.analysis_create, name='analysis_create'),
    path('analyses/<int:pk>/', views.analysis_detail, name='analysis_detail'), path('analyses/<int:pk>/suggestions/', views.suggestions, name='suggestions'),
    path('applications/', views.applications, name='applications'), path('applications/new/', views.application_edit, name='application_create'),
    path('applications/<int:pk>/edit/', views.application_edit, name='application_edit'),
    path('interviews/', views.interviews, name='interviews'), path('interviews/start/<int:pk>/', views.interview_start, name='interview_start'),
    path('interviews/<int:pk>/', views.interview_detail, name='interview_detail'), path('questions/<int:pk>/answer/', views.answer, name='answer'),
]
for kind in ['resume', 'analysis', 'application', 'interview']:
    urlpatterns.append(path(f'{kind}/<int:pk>/delete/', views.delete_object, {'kind': kind}, name=f'{kind}_delete'))
