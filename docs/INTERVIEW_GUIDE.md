# Explain CareerPilot AI in a placement interview

## A 60-second introduction

“I built CareerPilot AI to bring resume matching, interview practice and application tracking into one Django app. Users upload a resume, paste a job description and get an explainable text-similarity score using Scikit-learn TF-IDF and cosine similarity. I extract skills with a small alias dictionary, then optionally call Gemini for personalized suggestions and feedback. All records belong to the signed-in user. I used SQLite locally and configured PostgreSQL, Gunicorn and WhiteNoise for deployment.”

Do not claim you trained a language model or built a production hiring system. The project's value is integrating understandable components into a complete tested workflow.

## The request path

Browser form → Django URL → authenticated view → validated form → matching/AI service → ORM database write → rendered template.

Bootstrap supplies the responsive grid; custom CSS supplies the visual design. JavaScript only adds loading states, so core actions still work without it. Django templates escape user and model output.

## Database relationships

- User owns many resumes, analyses, applications and interview sessions.
- Resume has many analyses. Each analysis saves the job description, score, matched/missing skills and suggestions.
- Analysis has many interview sessions. Each session has five questions with answers and feedback.
- AIUsage has one row per user/day; an atomic conditional increment enforces the request cap.
- Foreign keys use cascading deletion. Editing a resume invalidates dependent reports.

An application tracker entry is independent of an analysis: users can track roles even without running a match.

## Questions you should be ready for

**Why TF-IDF?** It is fast, free, deterministic and explainable. Common words carry less weight. It is suitable for a medium-level lexical comparison, but not deep semantic understanding.

**What is cosine similarity?** Dot product of the document vectors divided by their lengths. It compares direction and yields 0–1 for these nonnegative TF-IDF vectors. Identical documents produce approximately 1; no overlapping useful terms produces 0.

**Is there model training?** The vectorizer fits vocabulary and IDF statistics on each resume/job pair. There is no labeled dataset or classifier training. Pairwise scores are not globally calibrated or directly equivalent across different roles.

**Why separate skills and score?** The score measures lexical overlap; the dictionary gives readable explanations. Keeping them separate avoids pretending an arbitrary blended metric is a hiring probability.

**Why Gemini as well?** TF-IDF cannot rewrite bullets or critique an interview answer. Gemini handles language-generation tasks while local code handles matching, validation and persistence. Its output can be wrong, so users review suggestions and never invent credentials.

**How do you protect data?** Authentication, owner filters on every record lookup, user-scoped choices, CSRF, escaped templates, server-side keys, explicit AI sharing consent, file/text limits and secure production settings. Original resume files are discarded after extraction.

**What if the API is unavailable?** Requests have connect/read timeouts. Provider errors, malformed responses and exhausted daily budgets use labelled local guidance. The rest of the application stays usable.

**Why not a React frontend or Celery?** Server-rendered forms and synchronous bounded calls are enough for a small portfolio app and easier to explain. A larger system could add background tasks and a JSON API when justified.

**What did you test?** Authentication, page rendering, extraction, validation, score behavior, CRUD, filtering, ownership isolation, CSRF, output escaping, consent, mocked Gemini success/timeouts and request limits. Explain which checks were local and which need a live provider account.

**What would you improve next?** Expand/maintain the skill dictionary, add semantic embeddings with an evaluation set, pagination, email recovery, auth rate limiting, background AI jobs and an explicit retention policy. These are future improvements, not implemented features.

## Suggested resume bullets

- Built a Django career assistant integrating resume parsing, TF-IDF/cosine matching, mock interviews and application-tracking CRUD with a responsive Bootstrap UI.
- Integrated Gemini REST API for opt-in resume guidance and interview feedback, with timeouts, daily usage limits and rule-based fallbacks.
- Implemented owner-scoped data access, automated workflow tests and PostgreSQL/Render deployment configuration.

Add a deployed URL or user count only after those facts are true. Avoid invented accuracy or performance percentages.
