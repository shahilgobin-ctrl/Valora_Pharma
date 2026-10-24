// Design-preview interactions only; no server writes.

  // Zoom controls
  const paper = document.getElementById('paper');
  let scale = 1;
  const setScale = s => { scale = Math.min(1.6, Math.max(.6, s)); paper.style.transform = 'scale(' + scale + ')'; };
  document.getElementById('zoom-in').addEventListener('click', () => setScale(scale + .15));
  document.getElementById('zoom-out').addEventListener('click', () => setScale(scale - .15));

  // Decision logic
  const reason = document.getElementById('reason');
  const hint = document.getElementById('hint');
  const badge = document.getElementById('status-badge');
  const toast = document.getElementById('toast');
  const buttons = [document.getElementById('approve'), document.getElementById('reject')];

  function notify(msg) {
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2600);
  }
  function finish(kind, label) {
    badge.className = 'badge ' + kind;
    badge.textContent = label;
    buttons.forEach(b => b.disabled = true);
    reason.disabled = true;
    notify('Prescription ' + label.toLowerCase());
  }
  reason.addEventListener('input', () => { reason.classList.remove('invalid'); hint.textContent = ''; });
  document.getElementById('approve').addEventListener('click', () => finish('approved', 'Approved'));
  document.getElementById('reject').addEventListener('click', () => {
    if (!reason.value.trim()) {
      reason.classList.add('invalid');
      hint.textContent = 'Add a reason before rejecting this prescription.';
      reason.focus();
      return;
    }
    finish('rejected', 'Rejected');
  });
