/**
 * User-facing copy that has to stay identical across the two scan forms.
 *
 * The URL field label appears on the public form, is negated in the login
 * form's test ("there is no site-URL field here"), and is quoted inside the
 * whole-host hint. Keeping the noun in one constant means renaming the field
 * — e.g. to "Root URL" — is a one-line change that can't leave a hint behind
 * saying something different from the label above it.
 */
export const SITE_URL_LABEL = "Site URL";

/** The same thing in running prose, for hints and helper text. */
export const SITE_URL_NOUN = "site URL";

export const WHOLE_HOST_HINT = `Ignores the ${SITE_URL_NOUN}’s path — every page on the host is in scope.`;

export const WHOLE_HOST_HINT_LOGIN = `Ignores the ${SITE_URL_NOUN}’s path, but never leaves the exact signed-in website origin.`;

/**
 * Where the in-app "Send feedback" action goes.
 *
 * This is the only outbound link Axcess offers, it opens only when a person
 * clicks it, and nothing about the current scan is attached: Asana forms have
 * no documented URL-prefill contract, so there is no supported way to carry
 * page context across, and inventing one would risk leaking a scanned URL.
 */
export const FEEDBACK_FORM_URL =
  "https://form.asana.com/?k=nRyyF2UKBYMXEj3v8CKCCA&d=939514425027676";
