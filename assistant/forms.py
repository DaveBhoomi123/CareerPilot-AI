from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Resume, Analysis, Application
from .services.extraction import extract_resume


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(label='Email address', max_length=254,
                             widget=forms.EmailInput(attrs={'autocomplete': 'email'}))

    class Meta(UserCreationForm.Meta):
        fields = ('username', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if self._meta.model.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(label='Email address', max_length=254,
                             widget=forms.EmailInput(attrs={'autocomplete': 'email'}))

class ResumeForm(forms.ModelForm):
    field_order = ['title', 'upload', 'text']
    upload = forms.FileField(required=False, help_text='PDF, DOCX or TXT · up to 5 MB. Files are extracted and discarded; only text is saved.')
    class Meta:
        model = Resume
        fields = ['title', 'text']
        widgets = {'text': forms.Textarea(attrs={'rows': 9, 'placeholder': 'Paste your resume here, or upload a document above.'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['text'].required = False

    def clean(self):
        data = super().clean()
        if data.get('upload'):
            data['text'] = extract_resume(data['upload'])
        if len(data.get('text', '').strip()) < 50:
            raise forms.ValidationError('Add at least 50 characters of resume text or upload a readable document.')
        return data

class AnalysisForm(forms.ModelForm):
    class Meta:
        model = Analysis
        fields = ['resume', 'role', 'job_description']
        widgets = {'job_description': forms.Textarea(attrs={'rows': 10})}
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resume'].queryset = Resume.objects.filter(owner=user)
    def clean_job_description(self):
        text = self.cleaned_data['job_description'].strip()
        if len(text) < 50:
            raise forms.ValidationError('Add a job description of at least 50 characters.')
        return text

class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ['company', 'role', 'url', 'status', 'applied_on', 'notes']
        widgets = {'applied_on': forms.DateInput(attrs={'type': 'date'}), 'notes': forms.Textarea(attrs={'rows': 4})}

class AnswerForm(forms.Form):
    answer = forms.CharField(min_length=20, max_length=6000, widget=forms.Textarea(attrs={'rows': 5, 'placeholder': 'Explain your approach, give an example, and share the result…'}))


class CareerChatForm(forms.Form):
    message = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={
        'rows': 3, 'placeholder': 'Ask about your resume, skills, job search or next interview…',
        'class': 'form-control',
    }))
    resume = forms.ModelChoiceField(queryset=Resume.objects.none(), required=False, empty_label='No resume', widget=forms.Select(attrs={'class': 'form-select'}))
    analysis = forms.ModelChoiceField(queryset=Analysis.objects.none(), required=False, empty_label='No job analysis', widget=forms.Select(attrs={'class': 'form-select'}))
    share_context = forms.BooleanField(required=False, label='Share the selected context with Gemini for this message')

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resume'].queryset = Resume.objects.filter(owner=user).order_by('-created_at')
        self.fields['analysis'].queryset = Analysis.objects.filter(owner=user, resume__owner=user).order_by('-created_at')

    def clean(self):
        data = super().clean()
        if data.get('resume') and data.get('analysis'):
            raise forms.ValidationError('Choose either a resume or a job analysis, not both.')
        if (data.get('resume') or data.get('analysis')) and not data.get('share_context'):
            raise forms.ValidationError('Confirm sharing the selected context, or choose no context.')
        return data
