from django.conf import settings
from django.db import models

class Resume(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    filename = models.CharField(max_length=255, blank=True)
    text = models.TextField(max_length=40000)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Analysis(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE)
    role = models.CharField(max_length=120)
    job_description = models.TextField(max_length=20000)
    score = models.FloatField()
    matched = models.JSONField(default=list)
    missing = models.JSONField(default=list)
    suggestions = models.TextField(blank=True)
    suggestion_source = models.CharField(max_length=30, default='Local guidance')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.role

class Application(models.Model):
    STATUS = [('saved', 'Saved'), ('applied', 'Applied'), ('interview', 'Interview'), ('offer', 'Offer'), ('rejected', 'Rejected')]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.CharField(max_length=120)
    role = models.CharField(max_length=120)
    url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='saved')
    applied_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, max_length=5000)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.role} at {self.company}'

class Interview(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    analysis = models.ForeignKey(Analysis, on_delete=models.CASCADE)
    source = models.CharField(max_length=30, default='Local practice')
    created_at = models.DateTimeField(auto_now_add=True)

class Question(models.Model):
    interview = models.ForeignKey(Interview, related_name='questions', on_delete=models.CASCADE)
    text = models.TextField()
    answer = models.TextField(blank=True, max_length=6000)
    feedback = models.TextField(blank=True)
    source = models.CharField(max_length=30, blank=True)

class AIUsage(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    day = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'day'], name='unique_user_ai_day')]
