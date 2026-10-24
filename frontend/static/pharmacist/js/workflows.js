'use strict';
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-add-row]');
  if (!button) return;
  const prefix = button.dataset.addRow;
  const count = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
  const max = document.getElementById(`id_${prefix}-MAX_NUM_FORMS`);
  const index = Number(count.value);
  if (index >= Number(max.value)) return;
  const template = document.getElementById(`${prefix}-empty`);
  const container = document.querySelector(`[data-formset="${prefix}"]`);
  container.insertAdjacentHTML('beforeend', template.innerHTML.replaceAll('__prefix__', String(index)));
  count.value = index + 1;
});
