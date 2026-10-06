/**
 * Complete a web address typed without its scheme.
 *
 * People type "example.edu/section/" or "localhost:8000", not
 * "https://example.edu/section/". Rejecting that with "Add https:// at the
 * start" made them do a step Axcess can do for them, so New scan adds the
 * scheme instead, and shows the completed address in the box when the reader
 * leaves it, so what will be scanned is never hidden (COGA "Making Content
 * Usable", https://www.w3.org/TR/coga-usable/: do not make people do work
 * the system can do for them).
 *
 * - A website: https://, the secure default, and the only scheme sign-in
 *   scans accept.
 * - localhost (or a *.localhost name) and an IP address, IPv4 such as
 *   192.168.1.10 or an IPv6 literal in brackets: http://. These are local
 *   development or network servers, which seldom have a certificate for an
 *   IP address or localhost, so https:// there would usually fail.
 * - Anything that already names a scheme ("https://", "http://", or any
 *   other "name:" that is not a port) is left exactly as typed, so a wrong
 *   scheme such as ftp:// still gets the form's own error.
 */

// "name://" or "name:" not followed by a digit. "localhost:8000" is a host
// and port, not the scheme "localhost:", which new URL() would read it as.
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:(?!\d)/i;
const IPV4 = /^\d{1,3}(?:\.\d{1,3}){3}$/;

export function withScheme(raw: string): string {
  const typed = raw.trim();
  if (!typed || HAS_SCHEME.test(typed)) return typed;
  // "//example.edu" is scheme-relative: keep everything after the slashes.
  const rest = typed.replace(/^\/\//, "");
  const authority = rest.split(/[/?#]/, 1)[0] ?? "";
  const hostAndPort = authority.slice(authority.lastIndexOf("@") + 1);
  const host = (
    hostAndPort.startsWith("[")
      ? hostAndPort.slice(0, hostAndPort.indexOf("]") + 1)
      : hostAndPort.split(":")[0]
  ).toLowerCase();
  const local =
    host === "localhost" || host.endsWith(".localhost") || IPV4.test(host) || host.startsWith("[");
  return `${local ? "http" : "https"}://${rest}`;
}
