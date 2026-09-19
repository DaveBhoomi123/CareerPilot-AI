"""Render untrusted assistant Markdown using a minimal HTML allowlist."""
import markdown
import nh3
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = {
    'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'em', 'ul', 'ol', 'li', 'pre', 'code', 'blockquote', 'hr',
}


@register.filter
def chat_markdown(value):
    html = markdown.markdown(str(value or ''), extensions=['fenced_code', 'sane_lists'])
    # Sanitize AFTER Markdown parsing. No attributes, links, images, styles,
    # embedded content or event handlers are allowed into the rendered reply.
    clean_html = nh3.clean(
        html, tags=ALLOWED_TAGS, attributes={}, link_rel=None,
        clean_content_tags={'script', 'style', 'iframe', 'object', 'svg', 'math'},
        strip_comments=True,
    )
    return mark_safe(clean_html)
