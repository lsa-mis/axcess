"""Held-out labelled pages for the form error check (WCAG SC 3.3.1).

Written without looking at how the check works, so these cases test it
fairly. Each case is labelled as a careful human evaluator would label it by
the success criterion: "If an input error is automatically detected, the item
that is in error is identified and the error is described to the user in
text." The page format (Case, the shared head and its helpers) comes from
form_error_cases.py.
"""

# The cases are small HTML pages written inline; wrapping their markup to
# 100 characters would make them harder to read than to lint.
# ruff: noqa: E501
from __future__ import annotations

from .form_error_cases import _CONTACT, Case, _contact

INDEPENDENT_CASES: list[Case] = [
    # ---------------------------------------------------------------- fail
    Case(
        "i01_tailwind_ring_no_form",
        "fail",
        "A group of fields with no form element gets Tailwind-style red rings and aria-invalid, but no text.",
        """
<div id="g" class="max-w-md space-y-4">
  <h2 class="text-xl font-semibold">Shipping address</h2>
  <div><label for="street" class="block text-sm">Street</label><input id="street" class="ring-1 ring-gray-300 rounded"></div>
  <div><label for="city" class="block text-sm">City</label><input id="city" class="ring-1 ring-gray-300 rounded"></div>
  <div><label for="zip" class="block text-sm">ZIP code</label><input id="zip" class="ring-1 ring-gray-300 rounded"></div>
  <p><button type="button" id="save" class="rounded bg-indigo-600 text-white px-4 py-2">Save address</button></p>
</div>
<style>
  .ring-gray-300 { box-shadow: 0 0 0 1px #d1d5db; }
  .ring-red-500 { box-shadow: 0 0 0 2px #ef4444; border-color: #ef4444; }
</style>
<script>
document.getElementById('save').addEventListener('click', () => {
  blanks(document.getElementById('g')).forEach(i => {
    i.classList.remove('ring-gray-300');
    i.classList.add('ring-red-500');
    i.setAttribute('aria-invalid', 'true');
  });
});
</script>""",
    ),
    Case(
        "i02_bootstrap_empty_feedback",
        "fail",
        "Bootstrap was-validated styling shows red borders and an icon, but the invalid-feedback boxes are empty.",
        """
<form id="f" class="needs-validation" novalidate>
  <h2>Request a callback</h2>
  <div class="mb-3"><label for="ph" class="form-label">Phone number</label><input id="ph" class="form-control" type="tel" required><div class="invalid-feedback"></div></div>
  <div class="mb-3"><label for="when" class="form-label">Best time to call</label>
    <select id="when" class="form-select" required><option value="">Choose a time</option><option>Morning</option><option>Afternoon</option></select>
    <div class="invalid-feedback"></div></div>
  <p><button class="btn btn-primary" type="submit">Request callback</button></p>
</form>
<style>
  .invalid-feedback { display: none; color: #dc3545; font-size: .875em; min-height: 1em; }
  .was-validated .form-control:invalid, .was-validated .form-select:invalid {
    border: 2px solid #dc3545; padding-right: 2rem;
    background: no-repeat right .5rem center / 1rem url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12'%3e%3ccircle cx='6' cy='6' r='5' fill='%23dc3545'/%3e%3c/svg%3e");
  }
  .was-validated :invalid ~ .invalid-feedback { display: block; }
</style>
<script>
const f = document.getElementById('f');
onSubmit(f, f => { if (!f.checkValidity()) f.classList.add('was-validated'); });
</script>""",
    ),
    Case(
        "i03_table_asterisk_turns_red",
        "fail",
        "In a table layout, the asterisk beside each empty field grows and turns red; the asterisk text never changes.",
        """
<form id="f" novalidate>
  <h2>Order free samples</h2>
  <table>
    <tr><th scope="row"><label for="co">Company</label></th><td><input id="co" required></td><td><span class="star" aria-hidden="true">*</span></td></tr>
    <tr><th scope="row"><label for="qty">Number of samples</label></th><td><input id="qty" type="number" required></td><td><span class="star" aria-hidden="true">*</span></td></tr>
    <tr><th scope="row"><label for="ship">Ship to</label></th><td><textarea id="ship" required></textarea></td><td><span class="star" aria-hidden="true">*</span></td></tr>
  </table>
  <p><button type="submit">Order samples</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => blanks(f).forEach(i => {
  const s = i.closest('tr').querySelector('.star');
  s.style.color = RED; s.style.fontSize = '1.6em'; s.style.fontWeight = 'bold';
}));
</script>""",
    ),
    Case(
        "i04_dialog_hint_turns_red",
        "fail",
        "In an open dialog, the field underline and its unchanged help text turn red; nothing says what is wrong.",
        """
<dialog open aria-labelledby="dt">
  <form id="f" novalidate>
    <h2 id="dt">Get your receipt by email</h2>
    <label for="em">Email</label><input id="em" class="md" type="email" required aria-describedby="em-help">
    <p id="em-help" class="help">We only use this to send your receipt.</p>
    <label for="nm">Name on receipt</label><input id="nm" class="md" required aria-describedby="nm-help">
    <p id="nm-help" class="help">Shown at the top of the receipt.</p>
    <p><button type="submit">Send receipt</button></p>
  </form>
</dialog>
<style>
  input.md { border: 0; border-bottom: 1px solid #767676; }
  .help { color: #555; font-size: .9em; margin: .25rem 0; }
</style>
<script>
const f = document.getElementById('f');
onSubmit(f, f => blanks(f).forEach(i => {
  i.style.borderBottom = '2px solid ' + RED;
  i.setAttribute('aria-invalid', 'true');
  document.getElementById(i.getAttribute('aria-describedby')).style.color = RED;
}));
</script>""",
    ),
    Case(
        "i05_warning_sign_character_only",
        "fail",
        "A warning-sign character appears beside each empty field with a red border; the symbol does not describe the error.",
        """
<form id="f" novalidate>
  <h2>Join the waiting list</h2>
  <label for="fn">First name</label><input id="fn" required>
  <label for="town">Town</label><input id="town" required>
  <p><button type="submit">Join waiting list</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => blanks(f).forEach(i => {
  red(i);
  after(i, '<span class="err" style="margin-left:.5rem;font-size:1.2em">&#9888;</span>');
}));
</script>""",
    ),
    Case(
        "i06_error_count_and_colour",
        "fail",
        "A banner says only how many errors there are, and the fields in error are shown by colour alone.",
        _contact("""onSubmit(f, f => {
  const bad = blanks(f);
  bad.forEach(red);
  f.querySelector('.count')?.remove();
  f.querySelector('h2').insertAdjacentHTML('afterend',
    '<p class="count err" role="alert">Fix ' + bad.length + ' errors to continue.</p>');
});"""),
    ),
    Case(
        "i07_banner_names_no_field",
        "fail",
        "A text banner says a required field is missing, but no field is named or marked.",
        """
<form id="f" novalidate>
  <h2>Book a table</h2>
  <label for="who">Name for the booking</label><input id="who" required>
  <label for="size">Party size</label><input id="size" type="number" min="1" required>
  <label for="day">Date</label><input id="day" type="date" required>
  <p id="msg"></p>
  <p><button type="submit">Book table</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => {
  if (blanks(f).length) {
    const m = document.getElementById('msg');
    m.className = 'err'; m.setAttribute('role', 'alert');
    m.textContent = 'A required field is missing.';
  }
});
</script>""",
    ),
    Case(
        "i08_primevue_rerender_class_only",
        "fail",
        "The whole form is re-rendered from scratch with PrimeVue-style p-invalid classes (red borders) and no message text.",
        """
<div id="app"></div>
<style>
  .p-inputtext { border: 1px solid #767676; border-radius: 6px; padding: .5rem; }
  .p-invalid { border: 2px solid #e24c4c; }
  .p-field { margin-bottom: 1rem; }
</style>
<script>
const fields = [['first', 'First name'], ['last', 'Last name'], ['org', 'Organisation']];
function render(invalid) {
  document.getElementById('app').innerHTML =
    '<form id="f" novalidate><h2>Register for the workshop</h2>' +
    fields.map(([id, label]) => '<div class="p-field"><label for="' + id + '">' + label + '</label>' +
      '<input id="' + id + '" name="' + id + '" class="p-inputtext' + (invalid.includes(id) ? ' p-invalid' : '') + '"' +
      (invalid.includes(id) ? ' aria-invalid="true"' : '') + '></div>').join('') +
    '<p><button type="submit" class="p-button">Register</button></p></form>';
  const f = document.getElementById('f');
  f.addEventListener('submit', e => {
    e.preventDefault();
    render(fields.map(x => x[0]).filter(id => !f.elements[id].value));
  });
}
render([]);
</script>""",
    ),
    Case(
        "i09_radio_group_legend_red",
        "fail",
        "An unanswered required radio group gets a red frame and a red legend background; the legend text is unchanged.",
        """
<form id="f" novalidate>
  <h2>How did you hear about us?</h2>
  <fieldset id="src"><legend>Pick one</legend>
    <label><input type="radio" name="src" value="friend"> A friend</label>
    <label><input type="radio" name="src" value="web"> A website</label>
    <label><input type="radio" name="src" value="other"> Somewhere else</label>
  </fieldset>
  <p><button type="submit">Continue</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => {
  if (!f.querySelector('input[name=src]:checked')) {
    const fs = document.getElementById('src');
    fs.style.border = '2px solid ' + RED;
    const lg = fs.querySelector('legend');
    lg.style.background = RED; lg.style.color = '#fff';
  }
});
</script>""",
    ),
    Case(
        "i10_message_hidden_by_css",
        "fail",
        "Error messages are added to the page but a stylesheet keeps them display:none, so only red borders show.",
        """
<form id="f" novalidate>
  <h2>Ask a librarian</h2>
  <label for="nm">Your name</label><input id="nm" required>
  <label for="q">Your question</label><textarea id="q" rows="3" required></textarea>
  <p><button type="submit">Send question</button></p>
</form>
<style>
  .field-error { display: none; }
  .field-error.visible { display: block; color: #b00020; }
</style>
<script>
const f = document.getElementById('f');
const text = { nm: 'Please enter your name.', q: 'Please enter your question.' };
onSubmit(f, f => blanks(f).forEach(i => {
  red(i);
  if (!document.getElementById(i.id + '-e')) after(i, '<span class="field-error" id="' + i.id + '-e">' + text[i.id] + '</span>');
}));
</script>""",
    ),
    # ---------------------------------------------------------------- pass
    Case(
        "i11_summary_links_other_words",
        "pass",
        "An error summary links to each empty field and describes it, using different words from the labels (first name for Given name).",
        """
<div id="sum"></div>
<form id="f" novalidate>
  <h2>Apply for a library card</h2>
  <label for="gn">Given name</label><input id="gn" required>
  <label for="fam">Family name</label><input id="fam" required>
  <label for="ce">Contact email</label><input id="ce" type="email" required>
  <p><button type="submit">Apply for card</button></p>
</form>
<script>
const f = document.getElementById('f');
const say = { gn: 'Enter your first name', fam: 'Enter your surname', ce: 'Enter an email address we can reach you at' };
onSubmit(f, f => {
  const bad = blanks(f);
  bad.forEach(red);
  const s = document.getElementById('sum');
  s.innerHTML = '<div role="alert" tabindex="-1" style="border:4px solid #b00020;padding:1rem"><h2>There is a problem</h2><ul>' +
    bad.map(i => '<li><a href="#' + i.id + '" class="err">' + say[i.id] + '</a></li>').join('') + '</ul></div>';
  s.firstChild.focus();
});
</script>""",
    ),
    Case(
        "i12_table_message_column",
        "pass",
        "A timesheet laid out as a table writes a message in each empty row's message cell naming the day.",
        """
<form id="f" novalidate>
  <h2>Weekly timesheet</h2>
  <table>
    <thead><tr><th scope="col">Day</th><th scope="col">Hours worked</th><th scope="col">Notes</th></tr></thead>
    <tbody>
      <tr><th scope="row"><label for="mon">Monday</label></th><td><input id="mon" type="number" min="0" max="24" required></td><td class="msg" id="mon-m"></td></tr>
      <tr><th scope="row"><label for="tue">Tuesday</label></th><td><input id="tue" type="number" min="0" max="24" required></td><td class="msg" id="tue-m"></td></tr>
      <tr><th scope="row"><label for="wed">Wednesday</label></th><td><input id="wed" type="number" min="0" max="24" required></td><td class="msg" id="wed-m"></td></tr>
    </tbody>
  </table>
  <p><button type="submit">Submit timesheet</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => blanks(f).forEach(i => {
  red(i);
  i.setAttribute('aria-describedby', i.id + '-m');
  const m = document.getElementById(i.id + '-m');
  m.className = 'msg err';
  m.textContent = 'Enter hours for ' + i.labels[0].textContent + ' (use 0 if you did not work).';
}));
</script>""",
    ),
    Case(
        "i13_rerender_with_messages",
        "pass",
        "The whole form is rebuilt on submit, and each empty field comes back with an Error: message tied to it.",
        """
<div id="root"></div>
<script>
const spec = [['pname', 'Project name', 'Give the project a name.'], ['repo', 'Repository address', 'Add the address of the code repository, for example https://example.org/team/app.']];
function draw(bad) {
  document.getElementById('root').innerHTML =
    '<form id="f" novalidate><h2>New project</h2>' +
    spec.map(([id, label, msg]) => '<div data-field="' + id + '"><label for="' + id + '">' + label + '</label>' +
      '<input id="' + id + '" name="' + id + '"' + (bad.includes(id) ? ' class="is-error" aria-invalid="true" aria-describedby="' + id + '-err"' : '') + '>' +
      (bad.includes(id) ? '<p class="err" id="' + id + '-err">Error: ' + msg + '</p>' : '') + '</div>').join('') +
    '<p><button type="submit">Create project</button></p></form>';
  const f = document.getElementById('f');
  f.addEventListener('submit', e => { e.preventDefault(); draw(spec.map(s => s[0]).filter(id => !f.elements[id].value)); });
}
draw([]);
</script>""",
    ),
    Case(
        "i14_dialog_inline_messages",
        "pass",
        "A form inside an open dialog puts a red text message under each empty field.",
        """
<dialog open aria-labelledby="rt">
  <form id="f" novalidate>
    <h2 id="rt">Report a broken link</h2>
    <label for="addr">Page address</label><input id="addr" type="url" required>
    <label for="what">What is wrong?</label><textarea id="what" rows="3" required></textarea>
    <p><button type="submit">Send report</button></p>
  </form>
</dialog>
<script>
const f = document.getElementById('f');
const msg = { addr: 'Page address is empty. Paste the address of the page with the broken link.', what: 'Tell us what is wrong with the link.' };
onSubmit(f, f => {
  f.querySelectorAll('.err').forEach(e => e.remove());
  blanks(f).forEach(i => { red(i); after(i, '<p class="err">' + msg[i.id] + '</p>'); });
});
</script>""",
    ),
    Case(
        "i15_plain_sentence_no_colour",
        "pass",
        "Each empty field gets a plain black sentence after it explaining what is missing, with no colour or icon.",
        _contact(
            """const say = {
  name: 'We need your name so we know who to reply to. This box is empty.',
  email: 'We cannot reply without your email address. Please add it here.' };
onSubmit(f, f => {
  f.querySelectorAll('.why').forEach(e => e.remove());
  blanks(f).forEach(i => after(i, '<p class="why" style="margin:.25rem 0">' + say[i.id] + '</p>'));
});""",
            _CONTACT.replace("Contact us", "Write to the editor"),
        ),
    ),
    Case(
        "i16_grid_status_list",
        "pass",
        "A two-column address grid lists each empty field by its label in a status box and outlines the fields.",
        """
<form id="f" novalidate>
  <h2>Billing address</h2>
  <div id="probs" role="status"></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 1.5rem;max-width:36rem">
    <div><label for="l1">Address line 1</label><input id="l1" required></div>
    <div><label for="cty">City</label><input id="cty" required></div>
    <div><label for="st">State</label><input id="st" required></div>
    <div><label for="pc">Postcode</label><input id="pc" required></div>
  </div>
  <p><button type="submit">Save billing address</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => {
  const bad = blanks(f);
  bad.forEach(i => i.classList.add('is-error'));
  document.getElementById('probs').innerHTML = bad.length ?
    '<p class="err">Please fix these:</p><ul class="err">' +
    bad.map(i => '<li>' + i.labels[0].textContent + ': this is empty</li>').join('') + '</ul>' : '';
});
</script>""",
    ),
    Case(
        "i17_label_text_extended",
        "pass",
        "Each empty field's label grows a red phrase saying the field is required and was left empty.",
        """
<form id="f" novalidate>
  <h2>Event reply</h2>
  <label for="gname">Guest name</label><input id="gname" required>
  <label for="meal">Meal choice</label>
  <select id="meal" required><option value="">Select a meal</option><option>Vegetarian</option><option>Fish</option></select>
  <p><button type="submit">Send reply</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => blanks(f).forEach(i => {
  const l = i.labels[0];
  if (!l.querySelector('.err')) l.insertAdjacentHTML('beforeend', ' <span class="err">(required: you left this empty)</span>');
  i.setAttribute('aria-invalid', 'true');
}));
</script>""",
    ),
    # ------------------------------------------------------ not_applicable
    Case(
        "i18_optional_feedback_thanks",
        "not_applicable",
        "Every field is optional; submitting empty replaces the form with a green thank-you message and check mark.",
        """
<form id="f" novalidate>
  <h2>Was this page useful?</h2>
  <label for="rate">Your rating (optional)</label>
  <select id="rate"><option value="">No rating</option><option>Useful</option><option>Not useful</option></select>
  <label for="cm">Comments (optional)</label><textarea id="cm" rows="3"></textarea>
  <p><button type="submit">Send feedback</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => {
  f.outerHTML = '<div role="status" style="color:#1b5e20;border:2px solid #1b5e20;padding:1rem">' +
    '<svg aria-hidden="true" width="16" height="16"><path d="M2 8l4 4 8-8" stroke="#1b5e20" stroke-width="2" fill="none"/></svg> Thanks for your feedback!</div>';
});
</script>""",
    ),
    Case(
        "i19_brand_red_draft_saved",
        "not_applicable",
        "A red-branded form, whose inputs are red-bordered from the start, saves an empty draft and says so in red text.",
        """
<header style="background:#b71c1c;color:#fff;padding:.5rem 1rem"><strong>Redline Press</strong></header>
<form id="f" novalidate>
  <h2>Pitch an article</h2>
  <label for="ttl">Working title</label><input id="ttl" class="brand">
  <label for="sum">Summary</label><textarea id="sum" class="brand" rows="3"></textarea>
  <p><button type="submit" style="background:#b71c1c;color:#fff;border:0;padding:.5rem 1rem">Save draft</button></p>
  <p id="state" role="status"></p>
</form>
<style>.brand { border: 2px solid #b71c1c; }</style>
<script>
const f = document.getElementById('f');
onSubmit(f, f => {
  const s = document.getElementById('state');
  s.style.color = '#b71c1c'; s.style.fontWeight = 'bold';
  s.textContent = 'Saved as a draft. You can finish it later.';
});
</script>""",
    ),
    Case(
        "i20_warning_style_tip",
        "not_applicable",
        "Saving empty optional preferences shows an amber warning-styled tip about defaults, which is not an input error.",
        """
<form id="f" novalidate>
  <h2>Display preferences</h2>
  <label for="tz">Time zone</label>
  <select id="tz"><option value="">Use my device time zone</option><option>UTC</option><option>America/Detroit</option></select>
  <label for="nick">Nickname shown in reports</label><input id="nick">
  <p><button type="submit">Save preferences</button></p>
  <div id="note" role="status"></div>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => {
  document.getElementById('note').innerHTML =
    '<p style="background:#fff3cd;border-left:4px solid #8a6d00;padding:.5rem;color:#4d3d00">' +
    '<span aria-hidden="true">&#9888;</span> Preferences saved. Heads up: blank fields use the default settings.</p>';
});
</script>""",
    ),
    # --------------------------------------------------------- not_checked
    Case(
        "i21_fetch_post_server_validates",
        "not_checked",
        "The form has no checks of its own and posts to the server with fetch, showing whatever the server answers.",
        """
<form id="f" novalidate action="/api/newsletter" method="post">
  <h2>Get the monthly newsletter</h2>
  <label for="nl">Email</label><input id="nl" name="email" type="email">
  <p id="out" role="status"></p>
  <p><button type="submit">Subscribe to newsletter</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => {
  fetch(f.action, { method: 'POST', body: new FormData(f) })
    .then(r => r.json())
    .then(d => { document.getElementById('out').textContent = d.message; })
    .catch(() => {});
});
</script>""",
    ),
    # -------------------------------------------------------------- native
    Case(
        "i22_native_select_and_number",
        "native",
        "No novalidate and no script: a required select and a required number field rely on the browser's own message.",
        """
<form id="f">
  <h2>Choose a delivery slot</h2>
  <label for="dday">Day</label>
  <select id="dday" name="day" required><option value="">Pick a day</option><option>Monday</option><option>Thursday</option></select>
  <label for="boxes">Number of boxes</label><input id="boxes" name="boxes" type="number" min="1" max="20" required>
  <p><button type="submit">Reserve slot</button></p>
</form>""",
    ),
    # ------------------------------------------------------------- skipped
    Case(
        "i23_close_account",
        "skipped",
        "A destructive close-account form with a Delete my account button must never be pressed.",
        """
<form id="f" novalidate>
  <h2>Close your account</h2>
  <p>This removes your saved scans for good.</p>
  <label for="conf">Type CLOSE to confirm</label><input id="conf" required>
  <p><button type="submit">Delete my account</button></p>
</form>
<script>
const f = document.getElementById('f');
onSubmit(f, f => blanks(f).forEach(i => { red(i); after(i, '<p class="err">Type CLOSE to confirm.</p>'); }));
</script>""",
    ),
    Case(
        "i24_header_site_search",
        "skipped",
        "A one-field site search box in the page header is a search form, which is never submitted.",
        """
<header style="display:flex;gap:1rem;align-items:center;border-bottom:1px solid #767676;padding:.5rem 0">
  <strong>City Library</strong>
  <form id="s" action="/search" method="get" style="display:flex;gap:.25rem">
    <label for="q" class="sr-only">Search the catalogue</label>
    <input id="q" name="q" type="search" placeholder="Title, author or topic" style="margin:0">
    <button type="submit">Go</button>
  </form>
</header>
<main><h1>Opening hours</h1><p>Monday to Friday, 9 to 6.</p></main>
<script>
const s = document.getElementById('s');
onSubmit(s, s => { const q = s.querySelector('#q'); if (!q.value) red(q); });
</script>""",
    ),
]
