from django.contrib import admin
from .models import Resume, Analysis, Application, Interview, Question, AIUsage
admin.site.register([Resume, Analysis, Application, Interview, Question, AIUsage])
