/* Sign in / create account form */
(function () {
  let mode = 'login';
  const form = document.getElementById('authForm');
  const nameField = document.getElementById('nameField');
  const err = document.getElementById('authError');
  const submit = document.getElementById('authSubmit');

  document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      mode = tab.dataset.mode;
      document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t === tab));
      nameField.hidden = mode !== 'register';
      form.name.required = mode === 'register';
      form.password.autocomplete = mode === 'register' ? 'new-password' : 'current-password';
      submit.textContent = mode === 'register' ? 'Create account' : 'Sign in';
      err.hidden = true;
    });
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    err.hidden = true;
    submit.disabled = true;
    try {
      const body = { email: form.email.value, password: form.password.value };
      if (mode === 'register') body.name = form.name.value;
      const res = await fetch(mode === 'register' ? '/api/register' : '/api/login', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'Something went wrong.');
      location.href = '/';
    } catch (ex) {
      err.textContent = ex.message; err.hidden = false;
    } finally { submit.disabled = false; }
  });
})();
