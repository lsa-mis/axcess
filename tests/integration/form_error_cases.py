"""Labelled pages for the form error check (WCAG SC 3.3.1 Error Identification).

Each case is one small page with one form and the outcome a careful human
evaluator would give it, so the check's precision and recall can be measured
(tests/integration/test_form_error_identification.py). Synthetic by
construction, like tests/quality/corpora/detection_precision_v1.json: the
numbers are regression evidence for these patterns, not a real-world accuracy
estimate (DETECTION_EFFICACY.md).

Expected outcomes:

* ``fail``: the form detects an error but does not identify the field in
  error and describe the error in text. The positive class.
* ``pass``: the error is identified and described in text.
* ``native``: only the browser's own validation message.
* ``not_applicable``: the form shows no sign of detecting an error.
* ``not_checked``: the form tries to send itself; the server's answer is
  unknown because the check blocks the request.
* ``skipped``: must never be submitted (sign-in, payment, destructive,
  CAPTCHA, search), or has nothing to submit empty.
* ``ambiguous``: evaluators disagree; reported, never scored.

Every page records ``window.__clicked`` when a button is pressed, so the test
can prove a skipped form was never touched.
"""

# The cases are small HTML pages written inline; wrapping their markup to
# 100 characters would make them harder to read than to lint.
# ruff: noqa: E501
from __future__ import annotations

from dataclasses import dataclass

# Shared by every page: the styles a plain form has, and small helpers the
# cases use to react to a submit.
_HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
  body { font: 16px/1.5 sans-serif; margin: 2rem; color: #1a1a1a; background: #fff; }
  label { display: block; margin-top: 1rem; }
  input, select, textarea { border: 1px solid #767676; padding: 4px; font: inherit; }
  input:focus, select:focus, textarea:focus { outline: 3px solid #1d5fbf; }
  .err { color: #b00020; }
  .is-error { border: 2px solid #c62828 !important; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
<script>
  window.__clicked = false;
  document.addEventListener('click', e => {
    if (e.target.closest('button, input[type=submit], [role=button]')) window.__clicked = true;
  }, true);
  const RED = '#c62828';
  const red = el => { el.style.border = '2px solid ' + RED; };
  const blanks = root => [...root.querySelectorAll('input, select, textarea')]
    .filter(f => (f.type === 'checkbox' || f.type === 'radio') ? !f.checked : !f.value);
  const onSubmit = (form, fn) => form.addEventListener('submit', e => { e.preventDefault(); fn(form); });
  const after = (el, html) => el.insertAdjacentHTML('afterend', html);
</script></head><body>
"""


@dataclass(frozen=True)
class Case:
    id: str
    expected: str
    note: str
    body: str

    def html(self) -> str:
        return _HEAD.replace("{title}", self.id) + self.body + "\n</body></html>\n"


# A two-field contact form, the base most cases change one thing in.
_CONTACT = """
<form id="f" novalidate>
  <h2>Contact us</h2>
  <label for="name">Name</label><input id="name" name="name" required>
  <label for="email">Email</label><input id="email" name="email" type="email" required>
  <p><button type="submit">Send message</button></p>
</form>
"""


def _contact(script: str, form: str = _CONTACT) -> str:
    return form + "<script>\nconst f = document.getElementById('f');\n" + script + "\n</script>"


CASES: list[Case] = [
    # ---------------------------------------------------------------- fail
    Case(
        "f01_border_only",
        "fail",
        "Empty fields get a red border; no text.",
        _contact("onSubmit(f, f => blanks(f).forEach(red));"),
    ),
    Case(
        "f02_aria_invalid_only",
        "fail",
        "aria-invalid=true only: nothing shown, nothing said.",
        _contact(
            "onSubmit(f, f => blanks(f).forEach(i => i.setAttribute('aria-invalid', 'true')));"
        ),
    ),
    Case(
        "f03_icon_only",
        "fail",
        "Red border and a hidden SVG warning icon; no text.",
        _contact("""onSubmit(f, f => blanks(f).forEach(i => { red(i);
           after(i, '<svg aria-hidden="true" width="16" height="16"><circle cx="8" cy="8" r="7" fill="#c62828"/></svg>'); }));"""),
    ),
    Case(
        "f04_image_of_text",
        "fail",
        "The message is a picture of text with empty alt text.",
        _contact("""onSubmit(f, f => blanks(f).forEach(i => { red(i);
           after(i, '<img alt="" width="160" height="20" src="data:image/svg+xml,' +
             encodeURIComponent('<svg xmlns=&quot;http://www.w3.org/2000/svg&quot; width=&quot;160&quot; height=&quot;20&quot;><text y=&quot;15&quot; fill=&quot;red&quot;>This field is required</text></svg>') + '">'); }));"""),
    ),
    Case(
        "f05_pink_background",
        "fail",
        "Field background turns pale pink; no text.",
        _contact("onSubmit(f, f => blanks(f).forEach(i => { i.style.background = '#ffd6d6'; }));"),
    ),
    Case(
        "f06_label_red",
        "fail",
        "Only the label turns red.",
        _contact("onSubmit(f, f => blanks(f).forEach(i => { i.labels[0].style.color = RED; }));"),
    ),
    Case(
        "f07_error_class",
        "fail",
        "Field gains an error class (red border); no text.",
        _contact("onSubmit(f, f => blanks(f).forEach(i => i.classList.add('is-error')));"),
    ),
    Case(
        "f08_checkbox_label_red",
        "fail",
        "A required checkbox's label turns red.",
        """
<form id="f" novalidate><h2>Terms</h2>
  <label><input type="checkbox" id="agree" name="agree"> I agree to the terms</label>
  <p><button type="submit">Continue</button></p></form>
<script>onSubmit(document.getElementById('f'), () => { document.querySelector('label').style.color = RED; });</script>""",
    ),
    Case(
        "f09_select_red",
        "fail",
        "A select with no choice gets a red border.",
        """
<form id="f" novalidate><h2>Your role</h2>
  <label for="role">Role</label><select id="role" name="role"><option value="">Choose one</option><option>Staff</option></select>
  <p><button type="submit">Submit</button></p></form>
<script>onSubmit(document.getElementById('f'), f => { red(f.querySelector('select')); });</script>""",
    ),
    Case(
        "f10_radio_legend_red",
        "fail",
        "A radio group's fieldset border and legend turn red.",
        """
<form id="f" novalidate><h2>Plan</h2>
  <fieldset id="fs"><legend>Choose a plan</legend>
    <label><input type="radio" name="plan" value="a"> Basic</label>
    <label><input type="radio" name="plan" value="b"> Plus</label></fieldset>
  <p><button type="submit">Submit</button></p></form>
<script>onSubmit(document.getElementById('f'), () => { const fs = document.getElementById('fs');
  fs.style.borderColor = RED; fs.querySelector('legend').style.color = RED; });</script>""",
    ),
    Case(
        "f11_textarea_red",
        "fail",
        "A textarea gets a red border.",
        """
<form id="f" novalidate><h2>Feedback</h2>
  <label for="msg">Your feedback</label><textarea id="msg" name="msg"></textarea>
  <label for="who">Your name</label><input id="who" name="who">
  <p><button type="submit">Submit feedback</button></p></form>
<script>onSubmit(document.getElementById('f'), f => red(f.querySelector('textarea')));</script>""",
    ),
    Case(
        "f12_many_fields",
        "fail",
        "Four fields turn red; no text.",
        """
<form id="f" novalidate><h2>Register for the event</h2>
  <label for="a">First name</label><input id="a"><label for="b">Last name</label><input id="b">
  <label for="c">Email</label><input id="c" type="email"><label for="d">Phone</label><input id="d" type="tel">
  <p><button type="submit">Register</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(red));</script>""",
    ),
    Case(
        "f13_formless_group",
        "fail",
        "No <form>: a div and a type=button Submit, red borders.",
        """
<div id="g"><h2>Request access</h2>
  <label for="n">Name</label><input id="n"><label for="r">Reason</label><input id="r">
  <p><button type="button" id="go">Submit request</button></p></div>
<script>document.getElementById('go').addEventListener('click', () => blanks(document.getElementById('g')).forEach(red));</script>""",
    ),
    Case(
        "f14_in_iframe",
        "fail",
        "The form is in a frame; red borders, no text.",
        """
<h1>Embedded form</h1>
<iframe title="Contact form" style="width:500px;height:300px" srcdoc="
<form id=f novalidate><label for=n>Name</label><input id=n style='border:1px solid #767676'>
<label for=e>Email</label><input id=e style='border:1px solid #767676'><button type=submit>Send</button></form>
<script>document.getElementById('f').addEventListener('submit', e => { e.preventDefault();
  for (const i of document.querySelectorAll('input')) if (!i.value) i.style.border = '2px solid #c62828'; });</script>"></iframe>""",
    ),
    Case(
        "f15_late_border",
        "fail",
        "Red borders appear 700 ms after the click.",
        _contact("onSubmit(f, f => setTimeout(() => blanks(f).forEach(red), 700));"),
    ),
    Case(
        "f16_hidden_text",
        "fail",
        "aria-invalid set and a message added inside a display:none box.",
        _contact("""onSubmit(f, f => blanks(f).forEach(i => { i.setAttribute('aria-invalid', 'true');
           after(i, '<div style="display:none"><span class="err">This field is required</span></div>'); }));"""),
    ),
    Case(
        "f17_asterisk_red",
        "fail",
        "Only the required asterisk in the label group turns red.",
        """
<form id="f" novalidate><h2>Sign up for updates</h2>
  <div><label for="n">Name <span class="ast">*</span></label><input id="n"></div>
  <div><label for="e">Email <span class="ast">*</span></label><input id="e" type="email"></div>
  <p><button type="submit">Sign up</button></p></form>
<script>onSubmit(document.getElementById('f'), () => document.querySelectorAll('.ast').forEach(a => a.style.color = RED));</script>""",
    ),
    Case(
        "f18_wrapper_border",
        "fail",
        "A wrapper box around each field turns red (Material style).",
        """
<form id="f" novalidate><h2>Your details</h2>
  <label for="n">Name</label><div class="box" style="border:1px solid #767676;padding:2px"><input id="n" style="border:0"></div>
  <label for="e">Email</label><div class="box" style="border:1px solid #767676;padding:2px"><input id="e" style="border:0"></div>
  <p><button type="submit">Save details</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(i => red(i.parentElement)));</script>""",
    ),
    Case(
        "f19_generic_summary_red",
        "fail",
        "'Please correct the errors below' plus red fields; no field named.",
        _contact("""onSubmit(f, f => { blanks(f).forEach(red);
           f.insertAdjacentHTML('afterbegin', '<p class="err" role="alert">Please correct the errors below.</p>'); });"""),
    ),
    Case(
        "f20_generic_no_mark",
        "fail",
        "'There was a problem with your submission.' Nothing marked or named.",
        _contact("""onSubmit(f, f => f.insertAdjacentHTML('afterbegin',
           '<p class="err">There was a problem with your submission.</p>'));"""),
    ),
    Case(
        "f21_shadow_dom",
        "fail",
        "Fields inside a web component's shadow DOM turn red (known gap).",
        """
<form id="f" novalidate><h2>Contact</h2><x-field label="Name"></x-field><x-field label="Email"></x-field>
  <p><button type="submit">Send</button></p></form>
<script>customElements.define('x-field', class extends HTMLElement { connectedCallback() {
  const r = this.attachShadow({mode: 'open'});
  r.innerHTML = '<label>' + this.getAttribute('label') + ' <input style="border:1px solid #767676"></label>'; } });
onSubmit(document.getElementById('f'), () => document.querySelectorAll('x-field').forEach(x =>
  x.shadowRoot.querySelector('input').style.border = '2px solid #c62828'));</script>""",
    ),
    Case(
        "f22_button_only",
        "fail",
        "Only the submit button turns red; fields unchanged, no text.",
        _contact(
            "onSubmit(f, f => { f.querySelector('button').style.background = RED; f.querySelector('button').style.color = '#fff'; });"
        ),
    ),
    Case(
        "f23_alert_generic",
        "fail",
        "alert('Error') and red fields; the message names no field.",
        _contact("onSubmit(f, f => { blanks(f).forEach(red); alert('Error'); });"),
    ),
    Case(
        "f24_partial",
        "fail",
        "Name gets a message; Email only turns red.",
        _contact("""onSubmit(f, f => { const [n, e] = [f.querySelector('#name'), f.querySelector('#email')];
           red(n); red(e); after(n, '<span class="err">Name is required</span>'); });"""),
    ),
    Case(
        "f25_outline_only",
        "fail",
        "A red outline on each field; no text.",
        _contact(
            "onSubmit(f, f => blanks(f).forEach(i => { i.style.outline = '2px solid ' + RED; }));"
        ),
    ),
    Case(
        "f26_glow_only",
        "fail",
        "A red box-shadow glow on each field; no text.",
        _contact(
            "onSubmit(f, f => blanks(f).forEach(i => { i.style.boxShadow = '0 0 0 3px rgba(198,40,40,.6)'; }));"
        ),
    ),
    Case(
        "f27_redraw_red",
        "fail",
        "The whole form is redrawn on submit with red borders; no text.",
        """
<div id="app"></div>
<script>function draw(bad) { app.innerHTML = '<form id="f" novalidate><h2>Contact us</h2>' +
  ['Name', 'Email'].map(l => '<label for="' + l + '">' + l + '</label><input id="' + l + '"' + (bad ? ' style="border:2px solid #c62828"' : '') + '>').join('') +
  '<p><button type="submit">Send message</button></p></form>';
  document.getElementById('f').addEventListener('submit', e => { e.preventDefault(); draw(true); }); }
draw(false);</script>""",
    ),
    # ---------------------------------------------------------------- pass
    Case(
        "p01_linked_text",
        "pass",
        "Text below each field, linked by aria-describedby, aria-invalid set.",
        _contact("""onSubmit(f, f => blanks(f).forEach(i => { red(i); i.setAttribute('aria-invalid', 'true');
           after(i, '<span id="' + i.id + '-err" class="err">' + i.labels[0].textContent + ' is required</span>');
           i.setAttribute('aria-describedby', i.id + '-err'); }));"""),
    ),
    Case(
        "p02_unlinked_text",
        "pass",
        "Text right after each field, not linked; red border.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"></div>
  <div><label for="email">Email</label><input id="email" type="email"></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(i => { red(i);
  after(i, '<div class="err">Enter your ' + i.labels[0].textContent.toLowerCase() + '</div>'); }));</script>""",
    ),
    Case(
        "p03_summary_names_fields",
        "pass",
        "An alert summary names each field; fields turn red.",
        _contact("""onSubmit(f, f => { blanks(f).forEach(red);
           f.insertAdjacentHTML('afterbegin', '<div role="alert" class="err"><p>There are 2 errors:</p><ul><li>Name is required</li><li>Email is required</li></ul></div>'); });"""),
    ),
    Case(
        "p04_generic_summary_inline",
        "pass",
        "A generic summary, and a message beside each field.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"></div>
  <div><label for="email">Email</label><input id="email" type="email"></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), f => {
  f.insertAdjacentHTML('afterbegin', '<p class="err">Please fix the errors below.</p>');
  blanks(f).forEach(i => { red(i); after(i, '<div class="err">This field is required</div>'); }); });</script>""",
    ),
    Case(
        "p05_native_required",
        "native",
        "required fields, no novalidate: the browser's own message.",
        """
<form id="f" onsubmit="event.preventDefault()"><h2>Contact us</h2>
  <label for="name">Name</label><input id="name" required>
  <label for="email">Email</label><input id="email" type="email" required>
  <p><button type="submit">Send message</button></p></form>""",
    ),
    Case(
        "p06_native_with_user_invalid",
        "native",
        "Native required plus red :user-invalid styling.",
        """
<style>input:user-invalid { border: 2px solid #c62828; }</style>
<form id="f" onsubmit="event.preventDefault()"><h2>Newsletter</h2>
  <label for="name">Name</label><input id="name" required>
  <label for="email">Email</label><input id="email" type="email" required>
  <p><button type="submit">Subscribe</button></p></form>""",
    ),
    Case(
        "p07_late_text",
        "pass",
        "The message appears 700 ms after the click.",
        _contact("""onSubmit(f, f => setTimeout(() => blanks(f).forEach(i => { red(i);
           after(i, '<span class="err">Please enter your ' + i.labels[0].textContent.toLowerCase() + '</span>'); }), 700));"""),
    ),
    Case(
        "p08_toast",
        "pass",
        "A role=alert toast names the fields, then disappears after 1 s.",
        _contact("""onSubmit(f, f => { const t = document.createElement('div'); t.setAttribute('role', 'alert');
           t.textContent = 'Name and Email are required.'; document.body.append(t); setTimeout(() => t.remove(), 1000); });"""),
    ),
    Case(
        "p09_revealed_message",
        "pass",
        "A message already in the page, hidden, is revealed.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"><span class="err" hidden id="ne">Please enter your name</span></div>
  <div><label for="email">Email</label><input id="email"><span class="err" hidden id="ee">Please enter your email</span></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), () => { ne.hidden = false; ee.hidden = false; });</script>""",
    ),
    Case(
        "p10_live_region",
        "pass",
        "An aria-live region is filled with a message naming the field.",
        _contact(
            """onSubmit(f, f => { document.getElementById('live').textContent = 'Please enter your name and email.'; });""",
            _CONTACT + '<div aria-live="polite" id="live"></div>',
        ),
    ),
    Case(
        "p11_formless_text",
        "pass",
        "No <form>: inline messages beside each field.",
        """
<div id="g"><h2>Request access</h2>
  <div><label for="n">Name</label><input id="n"></div><div><label for="r">Reason</label><input id="r"></div>
  <p><button type="button" id="go">Submit request</button></p></div>
<script>go.addEventListener('click', () => blanks(document.getElementById('g')).forEach(i => { red(i);
  after(i, '<div class="err">' + i.labels[0].textContent + ' is required</div>'); }));</script>""",
    ),
    Case(
        "p12_iframe_text",
        "pass",
        "The form is in a frame and shows text messages.",
        """
<h1>Embedded form</h1>
<iframe title="Contact form" style="width:500px;height:300px" srcdoc="
<form id=f novalidate><div><label for=n>Name</label><input id=n></div><div><label for=e>Email</label><input id=e></div>
<button type=submit>Send</button></form>
<script>document.getElementById('f').addEventListener('submit', e => { e.preventDefault();
  for (const i of document.querySelectorAll('input')) if (!i.value) i.insertAdjacentHTML('afterend', '<span>Required</span>'); });</script>"></iframe>""",
    ),
    Case(
        "p13_other_language_linked",
        "pass",
        "Spanish message, linked by aria-errormessage.",
        """
<form id="f" novalidate lang="es"><h2>Contacto</h2>
  <label for="nombre">Nombre</label><input id="nombre"><span id="ne"></span>
  <label for="correo">Correo</label><input id="correo"><span id="ce"></span>
  <p><button type="submit">Enviar</button></p></form>
<script>onSubmit(document.getElementById('f'), () => { for (const [i, m] of [[nombre, ne], [correo, ce]]) {
  i.setAttribute('aria-invalid', 'true'); i.setAttribute('aria-errormessage', m.id); m.textContent = 'Este campo es obligatorio'; } });</script>""",
    ),
    Case(
        "p14_upper_case",
        "pass",
        "'REQUIRED' in capitals beside each field.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"></div><div><label for="email">Email</label><input id="email"></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(i => after(i, '<b class="err">REQUIRED</b>')));</script>""",
    ),
    Case(
        "p15_checkbox_text",
        "pass",
        "A required checkbox: 'You must agree to the terms'.",
        """
<form id="f" novalidate><h2>Terms</h2>
  <div><label><input type="checkbox" id="agree"> I agree to the terms</label></div>
  <p><button type="submit">Continue</button></p></form>
<script>onSubmit(document.getElementById('f'), () => after(document.querySelector('label'), '<div class="err">You must agree to the terms</div>'));</script>""",
    ),
    Case(
        "p16_css_generated_text",
        "pass",
        "The message is CSS-generated text (::after content).",
        """
<style>.show::after { content: "Please enter your name"; color: #b00020; }</style>
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"><span id="m"></span></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), () => { m.className = 'show'; red(name); });</script>""",
    ),
    Case(
        "p17_alert_dialog_names",
        "pass",
        "alert() names the fields; nothing marked.",
        _contact("onSubmit(f, f => alert('Please enter your name and email.'));"),
    ),
    Case(
        "p18_single_field_generic",
        "pass",
        "One field; a generic 'This field is required' at the top.",
        """
<form id="f" novalidate><h2>Newsletter</h2>
  <label for="e">Email address</label><input id="e" type="email">
  <p><button type="submit">Subscribe</button></p></form>
<script>onSubmit(document.getElementById('f'), f => f.insertAdjacentHTML('afterbegin', '<p class="err" role="alert">This field is required.</p>'));</script>""",
    ),
    Case(
        "p19_custom_invalid_event",
        "pass",
        "Native required, with the page's own text shown on the invalid event.",
        """
<form id="f" onsubmit="event.preventDefault()"><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name" required></div>
  <div><label for="email">Email</label><input id="email" type="email" required></div>
  <p><button type="submit">Send message</button></p></form>
<script>document.querySelectorAll('input').forEach(i => i.addEventListener('invalid', e => { e.preventDefault();
  if (!i.nextElementSibling) after(i, '<span class="err">' + i.labels[0].textContent + ' is required</span>'); }));</script>""",
    ),
    Case(
        "p20_redraw_text",
        "pass",
        "The whole form is redrawn on submit with a message under each field.",
        """
<div id="app"></div>
<script>function draw(bad) { app.innerHTML = '<form id="f" novalidate><h2>Contact us</h2>' +
  ['Name', 'Email'].map(l => '<div><label for="' + l + '">' + l + '</label><input id="' + l + '">' +
    (bad ? '<span class="err">' + l + ' is required</span>' : '') + '</div>').join('') +
  '<p><button type="submit">Send message</button></p></form>';
  document.getElementById('f').addEventListener('submit', e => { e.preventDefault(); draw(true); }); }
draw(false);</script>""",
    ),
    # ------------------------------------------------------ not applicable
    Case(
        "n01_nothing_happens",
        "not_applicable",
        "The submit handler does nothing.",
        _contact("onSubmit(f, () => {});"),
    ),
    Case(
        "n02_success_message",
        "not_applicable",
        "Shows 'Thanks! We'll be in touch.' and sends nothing.",
        _contact(
            "onSubmit(f, f => f.insertAdjacentHTML('beforeend', '<p>Thanks! We\\'ll be in touch.</p>'));"
        ),
    ),
    Case(
        "n03_static_red_banner",
        "not_applicable",
        "A red banner was already on the page; nothing changes.",
        '<p class="err">Registration closes Friday.</p>' + _contact("onSubmit(f, () => {});"),
    ),
    Case(
        "n04_focus_ring",
        "not_applicable",
        "The handler only moves focus to the first field (blue ring).",
        _contact("onSubmit(f, f => f.querySelector('input').focus());"),
    ),
    Case(
        "n05_please_wait",
        "not_applicable",
        "The button changes to 'Please wait' and is disabled.",
        _contact(
            "onSubmit(f, f => { const b = f.querySelector('button'); b.textContent = 'Please wait'; b.disabled = true; });"
        ),
    ),
    Case(
        "n06_hover_style",
        "not_applicable",
        "Only the button's hover and active styles change.",
        """
<style>button:hover, button:active { background: #c62828; color: #fff; }</style>"""
        + _contact("onSubmit(f, () => {});"),
    ),
    Case(
        "n07_redraw_same",
        "not_applicable",
        "The whole form is redrawn on submit exactly as it was.",
        """
<div id="app"></div>
<script>function draw() { app.innerHTML = '<form id="f" novalidate><h2>Contact us</h2>' +
  ['Name', 'Email'].map(l => '<label for="' + l + '">' + l + '</label><input id="' + l + '">').join('') +
  '<p><button type="submit">Send message</button></p></form>';
  document.getElementById('f').addEventListener('submit', e => { e.preventDefault(); draw(); }); }
draw();</script>""",
    ),
    # --------------------------------------------------------- not checked
    Case(
        "c01_plain_post",
        "not_checked",
        "A plain POST form with optional fields.",
        """
<form method="post" action="/contact"><h2>Contact us</h2>
  <label for="name">Name</label><input id="name" name="name">
  <p><button type="submit">Send message</button></p></form>""",
    ),
    Case(
        "c02_fetch_then_error",
        "not_checked",
        "Sends with fetch; shows a network error after the blocked request.",
        _contact("""onSubmit(f, f => fetch('/api/contact', {method: 'POST', body: new FormData(f)})
           .catch(() => f.insertAdjacentHTML('afterbegin', '<p class="err">Something went wrong. Please try again.</p>')));"""),
    ),
    Case(
        "c03_get_form",
        "not_checked",
        "A GET form (not a search) with an optional field.",
        """
<form method="get" action="/report"><h2>Find a report</h2>
  <label for="team">Team name</label><input id="team" name="team">
  <p><button type="submit">Show report</button></p></form>""",
    ),
    Case(
        "c04_fetch_server_errors",
        "not_checked",
        "Sends with fetch; would show the server's field errors.",
        _contact("""onSubmit(f, f => fetch('/api/contact', {method: 'POST'}).then(r => r.json())
           .then(j => f.insertAdjacentHTML('afterbegin', '<p class="err">' + j.error + '</p>'))
           .catch(() => f.insertAdjacentHTML('afterbegin', '<p class="err">Error: could not send. Please check your connection.</p>')));"""),
    ),
    # ------------------------------------------------------------ skipped
    Case(
        "s01_sign_in",
        "skipped",
        "A sign-in form (password field).",
        """
<form id="f" novalidate><h2>Sign in</h2>
  <label for="u">Email</label><input id="u"><label for="p">Password</label><input id="p" type="password">
  <p><button type="submit">Sign in</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(red));</script>""",
    ),
    Case(
        "s02_payment",
        "skipped",
        "A payment form (card number field).",
        """
<form id="f" novalidate><h2>Billing</h2>
  <label for="cc">Card number</label><input id="cc" autocomplete="cc-number">
  <p><button type="submit">Continue</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(red));</script>""",
    ),
    Case(
        "s03_search",
        "skipped",
        "A search form (role=search).",
        """
<form role="search" id="f"><label for="q">Search the site</label><input id="q" name="q"><button type="submit">Go</button></form>""",
    ),
    Case(
        "s04_delete",
        "skipped",
        "A 'Delete account' form.",
        """
<form id="f" novalidate><h2>Danger zone</h2>
  <label for="c">Type your username to confirm</label><input id="c">
  <p><button type="submit">Delete account</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(red));</script>""",
    ),
    Case(
        "s05_captcha",
        "skipped",
        "A form with a reCAPTCHA box.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <label for="name">Name</label><input id="name"><div class="g-recaptcha" data-sitekey="x">[captcha]</div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(red));</script>""",
    ),
    Case(
        "s06_no_submit_control",
        "skipped",
        "No button: submitted only with Enter.",
        """
<form id="f" novalidate><h2>Quick note</h2><label for="n">Note</label><input id="n"></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(red));</script>""",
    ),
    Case(
        "s07_nothing_empty",
        "skipped",
        "Every field already has a value.",
        """
<form id="f" novalidate><h2>Update your profile</h2>
  <label for="n">Name</label><input id="n" value="Jordan"><label for="e">Email</label><input id="e" value="j@example.org">
  <p><button type="submit">Save profile</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(red));</script>""",
    ),
    Case(
        "s08_donate",
        "skipped",
        "A 'Donate' form.",
        """
<form id="f" novalidate><h2>Give today</h2>
  <label for="amt">Amount</label><input id="amt">
  <p><button type="submit">Donate</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(red));</script>""",
    ),
    # ------------------------------------------------------------ decoys
    # Written after the detector, to try to cause false positives: forms
    # that change on submit for reasons other than a validation error.
    Case(
        "d01_red_promo_text",
        "not_applicable",
        "A red 'Sale ends today!' line appears; no validation.",
        _contact(
            "onSubmit(f, f => f.insertAdjacentHTML('beforeend', '<p class=\"err\">Sale ends today!</p>'));"
        ),
    ),
    Case(
        "d02_green_success_border",
        "not_applicable",
        "Fields turn green with a check mark; 'Looks good'.",
        _contact("""onSubmit(f, f => f.querySelectorAll('input').forEach(i => { i.style.border = '2px solid #2e7d32';
           after(i, '<span style=\"color:#2e7d32\">Looks good</span>'); }));"""),
    ),
    Case(
        "d03_form_background_orange",
        "not_applicable",
        "The whole form gets a pale orange 'processing' background.",
        _contact("onSubmit(f, f => { f.style.background = '#fff3e0'; });"),
    ),
    Case(
        "d04_red_focus_ring_site",
        "not_applicable",
        "The site's focus ring is red; the handler only focuses the first field.",
        "<style>input:focus { outline: 3px solid #c62828 !important; }</style>"
        + _contact("onSubmit(f, f => f.querySelector('input').focus());"),
    ),
    Case(
        "d05_always_red_borders",
        "not_applicable",
        "Fields have red borders by design from the start; nothing changes.",
        "<style>input { border: 2px solid #c62828 !important; }</style>"
        + _contact("onSubmit(f, () => {});"),
    ),
    Case(
        "d06_beta_badge",
        "not_applicable",
        "An orange 'Beta' badge appears beside the button.",
        _contact(
            "onSubmit(f, f => f.querySelector('button').insertAdjacentHTML('afterend', '<span style=\"background:#e65100;color:#fff;padding:2px 6px\">Beta</span>'));"
        ),
    ),
    Case(
        "d07_success_with_please_check",
        "not_applicable",
        "Shows 'Thanks! Please check your inbox to confirm.' without sending.",
        _contact(
            "onSubmit(f, f => f.insertAdjacentHTML('beforeend', '<p style=\"color:#2e7d32\">Thanks! Please check your inbox to confirm.</p>'));"
        ),
    ),
    Case(
        "d08_success_with_required",
        "not_applicable",
        "Shows 'Request received. No further action is required.' without sending.",
        _contact(
            "onSubmit(f, f => f.insertAdjacentHTML('beforeend', '<p>Request received. No further action is required.</p>'));"
        ),
    ),
    Case(
        "d09_saved_draft_status",
        "not_applicable",
        "A role=status 'Saved as draft' note appears.",
        _contact(
            "onSubmit(f, f => f.insertAdjacentHTML('beforeend', '<p role=\"status\">Saved as draft</p>'));"
        ),
    ),
    Case(
        "d10_wizard_next_step",
        "not_applicable",
        "Step 1 is accepted; step 2 appears with the hint 'Enter your street address'.",
        """
<form id="f" novalidate><h2>Apply</h2>
  <div id="s1"><label for="n">Nickname (optional)</label><input id="n"></div>
  <div id="s2" hidden><p>Step 2 of 3</p><label for="st">Street</label><input id="st"><small>Enter your street address</small></div>
  <p><button type="submit">Next</button></p></form>
<script>onSubmit(document.getElementById('f'), () => { s1.hidden = true; s2.hidden = false; });</script>""",
    ),
    Case(
        "d11_red_asterisks_unchanged",
        "not_applicable",
        "Required asterisks are red from the start; nothing changes.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name <span style="color:#c62828">*</span></label><input id="name"></div>
  <div><label for="email">Email <span style="color:#c62828">*</span></label><input id="email"></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), () => {});</script>""",
    ),
    Case(
        "d12_button_pulse",
        "not_applicable",
        "The button pulses with a red glow; fields unchanged, no text.",
        _contact(
            "onSubmit(f, f => { f.querySelector('button').style.boxShadow = '0 0 0 4px rgba(198,40,40,.5)'; });"
        ),
    ),
    # ------------------------------------------------------------- blind
    # Written after the detector's last change and scored without tuning
    # anything in response: the honest estimate. Patterns from common form
    # libraries (Bootstrap, Angular, React Hook Form) and real-world markup.
    Case(
        "b01_bootstrap_no_feedback",
        "fail",
        "Bootstrap was-validated: :invalid fields turn red, no feedback text.",
        """
<style>.was-validated input:invalid { border: 2px solid #dc3545; }</style>
<form id="f" novalidate><h2>Shipping</h2>
  <label for="city">City</label><input id="city" required><label for="zip">Zip</label><input id="zip" required>
  <p><button type="submit">Continue to shipping</button></p></form>
<script>const f = document.getElementById('f'); f.addEventListener('submit', e => { e.preventDefault();
  f.checkValidity(); f.classList.add('was-validated'); });</script>""",
    ),
    Case(
        "b02_bootstrap_with_feedback",
        "pass",
        "Bootstrap was-validated with its invalid-feedback text.",
        """
<style>.feedback { display: none; color: #dc3545; } .was-validated input:invalid { border: 2px solid #dc3545; }
  .was-validated input:invalid ~ .feedback { display: block; }</style>
<form id="f" novalidate><h2>Shipping</h2>
  <div><label for="city">City</label><input id="city" required><div class="feedback">Please provide a valid city.</div></div>
  <div><label for="zip">Zip</label><input id="zip" required><div class="feedback">Please provide a valid zip.</div></div>
  <p><button type="submit">Continue to shipping</button></p></form>
<script>const f = document.getElementById('f'); f.addEventListener('submit', e => { e.preventDefault();
  f.checkValidity(); f.classList.add('was-validated'); });</script>""",
    ),
    Case(
        "b03_angular_classes",
        "fail",
        "Angular-style ng-invalid ng-touched classes, red border, no text.",
        """
<style>input.ng-invalid.ng-touched { border: 2px solid #c62828; }</style>"""
        + _contact(
            "onSubmit(f, f => blanks(f).forEach(i => i.classList.add('ng-invalid', 'ng-touched')));"
        ),
    ),
    Case(
        "b04_title_tooltip_only",
        "fail",
        "Red border and a title tooltip 'Required', seen only on hover.",
        _contact("onSubmit(f, f => blanks(f).forEach(i => { red(i); i.title = 'Required'; }));"),
    ),
    Case(
        "b05_label_gains_required",
        "pass",
        "The label changes to 'Name (required)'.",
        _contact(
            "onSubmit(f, f => blanks(f).forEach(i => { i.labels[0].textContent += ' (required)'; }));"
        ),
    ),
    Case(
        "b06_orange_with_text",
        "pass",
        "Orange border and 'Check this field' beside it.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"></div><div><label for="email">Email</label><input id="email"></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(i => { i.style.border = '2px solid #ff9800';
  after(i, '<small>Check this field</small>'); }));</script>""",
    ),
    Case(
        "b07_one_message_names_all",
        "pass",
        "Fields red; one red line at the bottom names both.",
        _contact("""onSubmit(f, f => { blanks(f).forEach(red);
           f.insertAdjacentHTML('beforeend', '<p class="err">Name and Email are required.</p>'); });"""),
    ),
    Case(
        "b08_errors_outside_form",
        "pass",
        "Fields red; red messages naming each field, below the form.",
        _contact(
            """onSubmit(f, f => { blanks(f).forEach(red);
           document.getElementById('out').innerHTML = '<p class="err">Name is required.</p><p class="err">Email is required.</p>'; });""",
            _CONTACT + '<div id="out"></div>',
        ),
    ),
    Case(
        "b09_counter_appears",
        "not_applicable",
        "A '0 / 500 characters' counter appears; nothing else.",
        _contact(
            "onSubmit(f, f => f.insertAdjacentHTML('beforeend', '<small>0 / 500 characters</small>'));"
        ),
    ),
    Case(
        "b10_checking_then_available",
        "not_applicable",
        "'Checking...' then a green 'Available'; no request.",
        _contact("""onSubmit(f, f => { f.insertAdjacentHTML('beforeend', '<small id="st">Checking...</small>');
           setTimeout(() => { st.textContent = 'Available'; st.style.color = '#2e7d32'; }, 300); });"""),
    ),
    Case(
        "b11_reminder_not_identifying",
        "fail",
        "A red 'Required fields are marked with *' appears; no field marked.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <p class="err" id="r" hidden>Required fields are marked with *</p>
  <label for="name">Name *</label><input id="name"><label for="email">Email *</label><input id="email">
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), () => { r.hidden = false; });</script>""",
    ),
    Case(
        "b12_rhf_role_alert",
        "pass",
        "React Hook Form style: aria-invalid and a role=alert message after each field.",
        _contact("""onSubmit(f, f => blanks(f).forEach(i => { i.setAttribute('aria-invalid', 'true');
           after(i, '<p role="alert">This field is required</p>'); }));"""),
    ),
    Case(
        "b13_confirm_modal",
        "not_applicable",
        "A confirmation box 'Are you sure you want to send this?' opens.",
        _contact("""onSubmit(f, f => document.body.insertAdjacentHTML('beforeend',
           '<div role="dialog" aria-modal="true"><p>Are you sure you want to send this?</p><button type="button">Yes</button></div>'));"""),
    ),
    Case(
        "b14_red_x_icons",
        "fail",
        "Valid fields get a green tick, empty ones a red X icon; no text.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"></div><div><label for="email">Email</label><input id="email" value="a@b.org"></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), f => f.querySelectorAll('input').forEach(i => after(i, i.value
  ? '<svg width="14" height="14" aria-hidden="true"><path d="M2 7l3 3 7-7" stroke="#2e7d32" fill="none"/></svg>'
  : '<svg width="14" height="14" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="#c62828"/></svg>')));</script>""",
    ),
    # ------------------------------------------------------------ blind 2
    # Written after the fixes the first blind batch led to, and scored
    # without tuning: the second honest estimate.
    Case(
        "h01_tailwind_classes",
        "fail",
        "Tailwind-style border-red-500 ring classes; no text.",
        """
<style>.border-red-500 { border: 2px solid #ef4444 !important; } .ring-red-500 { box-shadow: 0 0 0 2px #ef4444; }</style>"""
        + _contact(
            "onSubmit(f, f => blanks(f).forEach(i => i.classList.add('border-red-500', 'ring-red-500')));"
        ),
    ),
    Case(
        "h02_mui_outline",
        "fail",
        "MUI-style: the outline box and label turn red; no helper text.",
        """
<style>.box { position: relative; padding: 6px; } .box fieldset { position: absolute; inset: 0; margin: 0; border: 1px solid #767676; border-radius: 4px; pointer-events: none; }
  .Mui-error fieldset { border-color: #d32f2f; } .Mui-error label { color: #d32f2f; } .box input { border: 0; position: relative; }</style>
<form id="f" novalidate><h2>Your details</h2>
  <div class="box"><label for="n">Name</label><input id="n"><fieldset aria-hidden="true"></fieldset></div>
  <div class="box"><label for="e">Email</label><input id="e"><fieldset aria-hidden="true"></fieldset></div>
  <p><button type="submit">Save details</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(i => i.parentElement.classList.add('Mui-error')));</script>""",
    ),
    Case(
        "h03_invisible_tooltip_text",
        "fail",
        "aria-invalid and red border; the message sits in a tooltip with opacity 0.",
        _contact("""onSubmit(f, f => blanks(f).forEach(i => { red(i); i.setAttribute('aria-invalid', 'true');
           after(i, '<span style="opacity:0" class="err">This field is required</span>'); }));"""),
    ),
    Case(
        "h04_exclamation_only",
        "fail",
        "Red border and a red '!' beside each field; no words.",
        _contact(
            "onSubmit(f, f => blanks(f).forEach(i => { red(i); after(i, '<b class=\"err\">!</b>'); }));"
        ),
    ),
    Case(
        "h05_mixed_partial",
        "fail",
        "Select gets 'Choose a country'; the checkbox's label only turns red.",
        """
<form id="f" novalidate><h2>Registration</h2>
  <div><label for="c">Country</label><select id="c"><option value="">Choose</option><option>Canada</option></select></div>
  <div><label id="tl"><input type="checkbox" id="t"> I accept the terms</label></div>
  <p><button type="submit">Register</button></p></form>
<script>onSubmit(document.getElementById('f'), () => { red(c); after(c, '<span class="err">Choose a country</span>');
  tl.style.color = RED; });</script>""",
    ),
    Case(
        "h06_left_bar_only",
        "fail",
        "A red bar on the left of each field's container; no text.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div class="g" style="border-left:4px solid transparent;padding-left:8px"><label for="name">Name</label><input id="name"></div>
  <div class="g" style="border-left:4px solid transparent;padding-left:8px"><label for="email">Email</label><input id="email"></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), () => document.querySelectorAll('.g').forEach(g => g.style.borderLeftColor = RED));</script>""",
    ),
    Case(
        "h07_tailwind_linked_text",
        "pass",
        "Tailwind-style red classes plus linked text.",
        """
<style>.border-red-500 { border: 2px solid #ef4444 !important; }</style>"""
        + _contact("""onSubmit(f, f => blanks(f).forEach(i => { i.classList.add('border-red-500');
           after(i, '<p id="' + i.id + '-e" style="color:#b91c1c">' + i.labels[0].textContent + ' is required.</p>');
           i.setAttribute('aria-describedby', i.id + '-e'); }));"""),
    ),
    Case(
        "h08_govuk_pattern",
        "pass",
        "GOV.UK: summary with links, 'Error:' text above each field, red bar.",
        """
<form id="f" novalidate><h2>Apply</h2>
  <div class="grp" style="border-left:5px solid transparent;padding-left:10px"><label for="fn">Full name</label><input id="fn"></div>
  <div class="grp" style="border-left:5px solid transparent;padding-left:10px"><label for="em">Email address</label><input id="em"></div>
  <p><button type="submit">Continue</button></p></form>
<script>onSubmit(document.getElementById('f'), f => {
  f.insertAdjacentHTML('afterbegin', '<div role="alert"><h2>There is a problem</h2><ul><li><a href="#fn">Enter your full name</a></li><li><a href="#em">Enter your email address</a></li></ul></div>');
  document.querySelectorAll('.grp').forEach(g => { g.style.borderLeftColor = '#d4351c'; const i = g.querySelector('input');
    i.insertAdjacentHTML('beforebegin', '<p style="color:#d4351c">Error: Enter your ' + g.querySelector('label').textContent.toLowerCase() + '</p>'); }); });</script>""",
    ),
    Case(
        "h09_fake_delay_thanks",
        "not_applicable",
        "After a short fake delay, a green 'Thank you'; nothing sent.",
        _contact(
            "onSubmit(f, f => setTimeout(() => f.insertAdjacentHTML('beforeend', '<p style=\"color:#2e7d32\">Thank you</p>'), 300));"
        ),
    ),
    Case(
        "h10_unrelated_warning_toast",
        "not_applicable",
        "An orange role=alert 'Warning: your session will expire soon' appears.",
        _contact("""onSubmit(f, f => document.body.insertAdjacentHTML('beforeend',
           '<div role="alert" style="color:#e65100">Warning: your session will expire soon</div>'));"""),
    ),
    Case(
        "h11_yellow_highlight",
        "not_applicable",
        "Fields get a yellow 'review what you entered' highlight.",
        _contact(
            "onSubmit(f, f => f.querySelectorAll('input').forEach(i => { i.style.background = '#fff59d'; }));"
        ),
    ),
    Case(
        "h12_native_url",
        "native",
        "Native required type=url field.",
        """
<form id="f" onsubmit="event.preventDefault()"><h2>Your website</h2>
  <label for="u">Website address</label><input id="u" type="url" required>
  <p><button type="submit">Save website</button></p></form>""",
    ),
    Case(
        "h13_text_above_field",
        "pass",
        "'This field is required' appears above each field, inside its group.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"></div><div><label for="email">Email</label><input id="email"></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), f => blanks(f).forEach(i => { red(i);
  i.insertAdjacentHTML('beforebegin', '<span class="err">This field is required</span>'); }));</script>""",
    ),
    Case(
        "h14_summary_short_names",
        "pass",
        "Summary 'Full name - required; Email - required' for labels 'Full name' and 'Email address'.",
        """
<form id="f" novalidate><h2>Apply</h2>
  <label for="fn">Full name</label><input id="fn"><label for="em">Email address</label><input id="em">
  <p><button type="submit">Continue</button></p></form>
<script>onSubmit(document.getElementById('f'), f => { blanks(f).forEach(red);
  f.insertAdjacentHTML('afterbegin', '<div role="alert" class="err">2 errors: Full name - required; Email - required</div>'); });</script>""",
    ),
    # ---------------------------------------------------------- ambiguous
    Case(
        "a01_static_required_turns_red",
        "ambiguous",
        "'Required' was always shown; it turns red.",
        """
<form id="f" novalidate><h2>Contact us</h2>
  <div><label for="name">Name</label><input id="name"><small class="hint">Required</small></div>
  <div><label for="email">Email</label><input id="email"><small class="hint">Required</small></div>
  <p><button type="submit">Send message</button></p></form>
<script>onSubmit(document.getElementById('f'), () => document.querySelectorAll('.hint').forEach(h => h.style.color = RED));</script>""",
    ),
    Case(
        "a02_screen_reader_only_text",
        "ambiguous",
        "Red border plus a message only screen readers get.",
        _contact(
            """onSubmit(f, f => blanks(f).forEach(i => { red(i); after(i, '<span class="sr-only">This field is required</span>'); }));"""
        ),
    ),
    Case(
        "a03_placeholder_message",
        "ambiguous",
        "The placeholder becomes 'Required' and the border turns red.",
        _contact(
            "onSubmit(f, f => blanks(f).forEach(i => { red(i); i.placeholder = 'Required'; }));"
        ),
    ),
    Case(
        "a04_image_with_alt",
        "ambiguous",
        "The message is a picture of text, with alt text that says it.",
        _contact("""onSubmit(f, f => blanks(f).forEach(i => { red(i);
           after(i, '<img alt="This field is required" width="16" height="16" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">'); }));"""),
    ),
]
