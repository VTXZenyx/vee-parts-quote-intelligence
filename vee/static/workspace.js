document.querySelectorAll('[data-print]').forEach((button) => {
  button.addEventListener('click', () => window.print());
});

const quoteEditor = document.querySelector('[data-quote-editor]');
const approval = document.querySelector('.approval button');
if (quoteEditor && approval) {
  const unsaved = document.querySelector('[data-unsaved]');
  const fields = [...quoteEditor.querySelectorAll('input[type="number"], textarea')];
  const showUnsaved = (dirty) => {
    approval.disabled = dirty;
    unsaved.hidden = !dirty;
  };
  const checkEdits = () => showUnsaved(fields.some((field) => field.value !== field.defaultValue));
  quoteEditor.addEventListener('input', checkEdits);
  quoteEditor.addEventListener('reset', () => showUnsaved(false));
  window.addEventListener('pageshow', checkEdits);
}

const processingForm = document.querySelector('[data-processing-form]');
if (processingForm) {
  const button = processingForm.querySelector('button');
  const progress = processingForm.querySelector('[role="status"]');
  processingForm.addEventListener('submit', () => {
    button.disabled = true;
    progress.textContent = 'Processing the selected message…';
  });
  window.addEventListener('pageshow', () => {
    button.disabled = false;
    progress.textContent = '';
  });
}
