document.querySelectorAll('[data-print]').forEach((button) => {
  button.addEventListener('click', () => window.print());
});

const quoteEditor = document.querySelector('[data-quote-editor]');
const approval = document.querySelector('.approval button');
if (quoteEditor && approval) {
  const unsaved = document.querySelector('[data-unsaved]');
  quoteEditor.addEventListener('input', () => {
    approval.disabled = true;
    unsaved.hidden = false;
  });
  quoteEditor.addEventListener('reset', () => {
    approval.disabled = false;
    unsaved.hidden = true;
  });
}
