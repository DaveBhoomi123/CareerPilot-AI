"""Transparent lexical matching: no trained model or paid service required."""
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SKILLS = {
    'Python': ['python'], 'Django': ['django'], 'Flask': ['flask'],
    'JavaScript': ['javascript', 'js'], 'TypeScript': ['typescript'],
    'HTML': ['html', 'html5'], 'CSS': ['css', 'css3'], 'Bootstrap': ['bootstrap'],
    'React': ['react', 'reactjs'], 'Node.js': ['node.js', 'nodejs'],
    'SQL': ['sql'], 'PostgreSQL': ['postgresql', 'postgres'], 'SQLite': ['sqlite'],
    'MySQL': ['mysql'], 'MongoDB': ['mongodb'], 'Git': ['git'], 'GitHub': ['github'],
    'REST APIs': ['rest', 'restful', 'rest api'], 'Docker': ['docker'],
    'AWS': ['aws', 'amazon web services'], 'Linux': ['linux'],
    'Java': ['java'], 'C++': ['c++'], 'C#': ['c#'], '.NET': ['.net', 'dotnet'],
    'Machine learning': ['machine learning', 'ml'], 'Scikit-learn': ['scikit-learn', 'sklearn'],
    'Pandas': ['pandas'], 'NumPy': ['numpy'], 'Excel': ['excel'],
    'Power BI': ['power bi', 'powerbi'], 'Tableau': ['tableau'],
    'Testing': ['testing', 'pytest', 'unit tests'], 'Agile': ['agile', 'scrum'],
    'Communication': ['communication'], 'Problem solving': ['problem solving', 'problem-solving'],
    'Data structures': ['data structures'], 'Algorithms': ['algorithms'],
}

def skills_in(text):
    return {name for name, aliases in SKILLS.items() if any(re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text, re.I) for alias in aliases)}

def match_resume(resume, job):
    try:
        vectors = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), max_features=12000).fit_transform([resume, job])
        score = round(float(cosine_similarity(vectors[0], vectors[1])[0][0]) * 100, 1)
    except ValueError:
        score = 0.0
    required, present = skills_in(job), skills_in(resume)
    return {'score': score, 'matched': sorted(required & present), 'missing': sorted(required - present)}
