// Progressive enhancement: all workflows still work without JavaScript.
document.querySelectorAll('form[data-busy]').forEach(form => {
  form.addEventListener('submit', () => {
    const button = form.querySelector('button[type="submit"], button:not([type])');
    if (button) { button.disabled = true; button.textContent = 'Working…'; }
    form.setAttribute('aria-busy', 'true');
  });
});
window.addEventListener('pageshow', event => {
  if (event.persisted) window.location.reload();
});

// Quick prompts only fill the composer; the user reviews and submits the form.
document.querySelectorAll('[data-chat-prompt]').forEach(button => {
  button.addEventListener('click', () => {
    const input = document.querySelector('[data-chat-form] textarea[name="message"]');
    if (input) { input.value = button.dataset.chatPrompt; input.focus(); }
  });
});
const chatForm = document.querySelector('[data-chat-form]');
if (chatForm) {
  chatForm.addEventListener('submit', () => {
    chatForm.querySelector('.chat-loading').hidden = false;
    document.querySelectorAll('[data-chat-prompt]').forEach(button => button.disabled = true);
  });
  const transcript = document.querySelector('.chat-transcript');
  transcript.scrollTop = transcript.scrollHeight;
}
