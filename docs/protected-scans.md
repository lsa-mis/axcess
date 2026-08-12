# Protected scans: authorized, manual authentication only

Protected scans are an opt-in deployment feature for an authorized
accessibility evaluation of a 1FA- or MFA-protected web application. They are
not a way to automate sign-in, bypass a control, test an IdP, or turn Axcess
into a general-purpose authenticated browser.

> Do not enable this mode with only `AUDIT_ACCESS_TOKEN`, a normal LAN
> deployment, or the local development KMS adapter. It requires a U-M-approved
> identity-aware proxy, companion mTLS deployment, and managed key-wrapping
> service. Until those controls are in place, use public scans only.

## The security boundary

The auditor, not Axcess, completes password entry and any MFA in a headed
Chromium window on the auditor's computer. Axcess never asks for, reads from a
credential form, forwards, or exports a password, OTP, passkey, recovery code,
CAPTCHA response, browser cookie, bearer token, authorization header, or
Playwright `storageState`.

```text
identity-aware proxy                      auditor's computer
  verified person + group                         headed Chromium
          |                                             |
          v                                             v
  protected Axcess UI -- one-time enrollment --> axcess-companion
          ^                         mTLS only           |
          |                                             | manual sign-in
          |                         opaque, redacted    v
          +------------------- issue index <---- approved application
```

Only a narrow, non-sensitive issue index returns to the Axcess host: opaque
page and occurrence keys, pipeline/rule identifiers, WCAG references, impact,
and counters. Real application URLs, selectors, page text, OCR text,
screenshots, raw HTML, and browser session state are not returned to Axcess.
The companion closes the browser and removes its dedicated ephemeral
profile/cache as described below.

| Axcess may do | Axcess must not do |
| --- | --- |
| Open a local headed browser and wait for the auditor to sign in. | Collect, prompt for, replay, or persist credentials or MFA factors. |
| Run allowed read-only checks after the auditor returns to an approved application page. | Bypass MFA, CAPTCHA, WAF, conditional access, or a login redirect. |
| Send one-use browser state to the local Alfa child process through memory/stdin only. | Write application-managed `storageState`, cookies, headers, or a reusable browser profile to disk. |
| Retain a bounded, non-sensitive issue index and outcome-only manual checks. | Accept reviewer attachments or companion artifact uploads in v1. |

An accessibility evaluation is not a conformance certificate, a penetration
test, or authorization to exercise application features. A nominal `GET` can
still have target-side effects, so the target owner must explicitly authorize
the rate, scope, and dedicated least-privilege audit account.

Exact approved target, authentication, and CDN origins are accepted only long
enough to validate the draft and encrypt its scan-bound companion work
specification. Ordinary SQLite metadata retains only the number of origins in
each scope and a deployment-HMAC-derived opaque tag; it does not retain or
display the actual origins after creation. The paired companion receives the
exact scope only after mTLS verification and work-spec decryption.

That encrypted work item also carries a random, per-report HMAC key. The
companion uses it only in memory to derive opaque page and finding-occurrence
aliases. A retry or manual re-authentication therefore updates the same
non-sensitive index entry instead of inflating coverage; another report cannot
correlate those aliases. The key is never returned to the browser, ordinary
SQLite metadata, logs, exports, or configuration. Existing pre-v3 companion
work is intentionally interrupted by migration rather than resumed with
retry-unsafe random aliases.

### Browser temporary profile and cache

Nonpersistent Playwright contexts are not a promise of zero disk writes:
Chromium/Playwright can create an OS temporary profile and cache while the
headed browser runs, and those files can contain session material. The
companion therefore uses a **dedicated ephemeral profile/cache directory**
created with `0700` permissions for the auditor account. It does not save a
reusable `storageState` or managed browser profile.

On normal completion, interruption, or authentication expiry, the companion
closes Chromium and removes that directory immediately. At companion startup,
it also performs bounded cleanup of abandoned protected profile/cache
directories left by a crash. This is a containment and lifecycle control, not
secure deletion of every storage block: production deployment must place this
ephemeral location on organization-managed **encrypted OS ephemeral storage**,
limit it to the auditor account, and ensure backup/synchronization products do
not capture it. Treat a crash before cleanup as a potential session exposure
under the deployment's incident procedure.

## Required deployment controls

This mode is disabled by default (`AUDIT_PROTECTED_SCANS_ENABLED=false`). A
production deployment needs all of the following before the protected-scan UI
is made available.

1. **Written target authorization.** Record the target owner, environment,
   exact HTTPS target/auth/CDN origins, data classification, permitted rate and
   page limits, and the least-privilege audit account. Production targets need
   explicit owner approval; use staging where practical. Axcess validates the
   exact origins and encrypts them into the scan-bound work specification; the
   ordinary report record contains only scope counts and opaque HMAC tags.
2. **Identity-aware proxy for people.** The proxy must authenticate the person,
   map the approved group (default `axcess-protected-scan`), and inject the
   configured identity, group, timestamp, high-entropy assertion nonce (JTI),
   and HMAC signature headers. The assertion is method/path/nonce-bound and
   short-lived. For the default header names, the proxy signs the UTF-8 bytes
   of this exact newline-separated input with HMAC-SHA-256:

   ```text
   UPPERCASE_HTTP_METHOD
   PATH_AS_AXCESS_RECEIVES_IT
   UNIX_TIMESTAMP_SECONDS
   UNIQUE_ASSERTION_NONCE
   IDENTITY_SUBJECT
   COMMA_JOINED_SORTED_GROUPS
   ```

   `PATH_AS_AXCESS_RECEIVES_IT` is the application path only—do not include a
   host, query string, or body—and must match the post-proxy path Axcess sees.
   Issue a new, unguessable nonce and signature for **every state-changing
   browser request**. Axcess retains a bounded, short-lived in-process replay
   cache for those requests; it may tolerate reuse for read-only polling, but
   that tolerance is not permission to reuse a mutation assertion. The proxy
   must strip every client-supplied protected identity header before it writes
   its own values (defaults: `X-Axcess-Identity`, `X-Axcess-Groups`,
   `X-Axcess-Timestamp`, `X-Axcess-Identity-Nonce`, and
   `X-Axcess-Signature`). It must also strip the configured companion mTLS
   verification/fingerprint headers from inbound traffic. Axcess must be
   reachable only through that trusted proxy; never let a client reach the app
   listener directly. `AUDIT_ACCESS_TOKEN` remains an ingress gate for public
   scans only; it is not protected-report authorization.
3. **mTLS proxy boundary for companions.** The TLS terminator must require the
   companion certificate on `/api/agents/*`, verify it, strip externally
   supplied mTLS headers, and inject only its verified certificate fingerprint
   and verification status. It must also inject a separate, short-lived HMAC
   assertion using `AUDIT_PROTECTED_AGENT_PROXY_HMAC_SECRET`; the companion
   never receives that secret. Axcess rejects unsigned mTLS headers, so a
   client that reaches the application listener cannot impersonate a proxy by
   setting `X-SSL-Client-*` itself. The application binds that fingerprint to
   exactly one claimed enrollment and scan.

   For the default header names, the companion-proxy HMAC is HMAC-SHA-256 of
   this exact UTF-8, newline-separated input. Lower-case the verification
   value and certificate fingerprint before signing; `PATH_AS_AXCESS_RECEIVES_IT`
   has the same path-only rules as the human identity assertion above.

   ```text
   UPPERCASE_HTTP_METHOD
   PATH_AS_AXCESS_RECEIVES_IT
   UNIX_TIMESTAMP_SECONDS
   UNIQUE_AGENT_ASSERTION_NONCE
   LOWERCASE_MTLS_VERIFICATION_VALUE
   LOWERCASE_CERTIFICATE_FINGERPRINT
   LOWERCASE_SHA256_OF_EXACT_RAW_REQUEST_BODY
   ```

   The proxy injects a new high-entropy nonce in `X-Axcess-Agent-Nonce`, the
   lowercase SHA-256 digest of the exact raw body in
   `X-Axcess-Agent-Body-SHA256`, the timestamp in
   `X-Axcess-Agent-Timestamp`, and the hex signature in
   `X-Axcess-Agent-Signature` (or the configured header names). The app
   recomputes the body digest, rejects query-bearing agent requests, and keeps
   a bounded short-lived replay cache for a signed assertion. Axcess accepts
   assertions only for the configured short lifetime (60 seconds by default).
   The proxy must keep the app listener private; this HMAC is a fail-closed
   attestation boundary, not a replacement for mTLS.
4. **Managed envelope-key wrapping.** Provide an approved U-M KMS/secret
   manager implementation of `KeyWrappingKms` through the administrator-owned
   `AUDIT_PROTECTED_KMS_VAULT_FACTORY` (or an equivalent trusted
   `create_app` embedding). The shipped `DeterministicLocalKms` adapter is for
   tests/development only and cannot create an enabled protected scan. Every
   protected environment, including a
   staging pilot, requires irreversible per-scan
   `destroy_scan_key`/grant revocation: deleting a wrapped DEK from SQLite
   alone does not make backups encrypted under a shared KEK unreadable. A
   stock `audit serve` process has no U-M KMS adapter; a production ASGI entry
   point must inject the managed vault.
5. **Private transport and logs.** Use HTTPS, restrict the host to the private
   network/proxy, and disable request/response-body and query logging on the
   proxy and app path. In particular, the companion work response contains an
   encrypted-work-spec-derived target scope and one-use opaque-index key; it
   must never reach access logs, traces, or observability payload capture. Do
   not put pairing codes, private keys, or target secrets in shell
   history, tickets, dashboards, environment variables, or support logs. Set
   the proxy's protected-route request-body limit no higher than
   `AUDIT_PROTECTED_REQUEST_BODY_MAX_BYTES` (1,000,000 bytes by default), and
   set request-header/body-read timeouts there as well. The app independently
   counts streamed bodies before FastAPI parses them, but the proxy is the
   boundary that must absorb slow or chunked connections before they consume
   app workers.
6. **Auditor workstation controls.** Provision a managed companion certificate through
   the approved PKI/MDM process. Before creating a pairing code, the auditor
   enters that certificate's SHA-256 public-certificate fingerprint in Axcess;
   the resulting enrollment is usable only by that exact certificate. Axcess
   does not issue certificates or receive private keys. Protect the private
   key with the organization-approved local key store or tightly permissioned
   file; it is not target session material, but it is still a credential for
   the companion service.

   Axcess deliberately adapts the proposed service-issued pairing certificate
   to U-M-managed PKI: it never generates a companion private key or
   certificate. The browser creates a proxy-authorized, certificate-prebound
   enrollment under `/api/protected-scans/{scanId}/agent-enrollments`; the
   companion's mTLS-only `POST /api/agents/enroll` is the one-time **claim**
   operation for that enrollment. There is no separate unauthenticated
   `/claim` endpoint. This keeps the pairing code bound to both the report and
   a pre-approved managed device credential.

The relevant settings establish the adapter boundary, rather than replacing
these deployment controls:

```text
AUDIT_PROTECTED_SCANS_ENABLED=true
AUDIT_PROTECTED_PROXY_HMAC_SECRET=<managed secret>
AUDIT_PROTECTED_AGENT_PROXY_HMAC_SECRET=<different managed proxy secret>
AUDIT_PROTECTED_REQUIRED_GROUP=axcess-protected-scan
AUDIT_PROTECTED_IDENTITY_NONCE_HEADER=x-axcess-identity-nonce
AUDIT_PROTECTED_PUBLIC_ORIGIN=https://axcess.example.umich.edu
AUDIT_PROTECTED_KMS_KEY_ID=<managed KMS key identifier>
AUDIT_PROTECTED_KMS_VAULT_FACTORY=um_axcess_kms:build_protected_vault
```

`AUDIT_PROTECTED_PUBLIC_ORIGIN` is a configured exact HTTPS origin, not a
request-derived `Host`, `Forwarded`, or `X-Forwarded-*` value. It is the
authoritative external browser origin for protected same-origin checks and the
only origin Axcess uses when it renders companion commands. It must be the
public HTTPS origin users and companions actually reach (with an optional
explicit non-default port, but no path, query, fragment, or userinfo). A
malicious request header therefore cannot direct a paired companion to another
service or make a protected browser mutation appear same-origin.

Do not set `AUDIT_PROTECTED_ALLOW_LOCAL_KMS` or
`AUDIT_PROTECTED_LOCAL_KMS_SEED` outside isolated development/test use.

## Auditor workflow

1. In **New protected scan**, enter only the approval and scope metadata. The
   seed and every approved origin must be an exact HTTPS origin—no wildcards,
   credentials/userinfo, paths, secret-bearing query strings, IP literals, or
   private-network hosts. The exact origins are encrypted into the scan-bound
   companion work item; after creation, the report workspace shows only
   origin counts and opaque scope tags.
2. Confirm target-owner authorization and the least-privilege-account
   acknowledgement. Select axe, Alfa, or both; optional local AI stays off by
   default.
3. From the protected report page, enter the SHA-256 fingerprint of the
   pre-provisioned companion certificate and create a one-time companion
   enrollment. The UI reveals the pairing code once. It is stored only as an
   scrypt verifier on the service, and the pairing code is pre-bound to that
   certificate fingerprint.
4. On the auditor's computer, run the displayed commands. The code is requested by
   a private terminal prompt, not accepted as a command argument:

   ```bash
   axcess-companion pair \
     --server https://axcess.example.umich.edu \
     --enrollment-id <one-time-enrollment-id> \
     --certificate /secure/path/companion-cert.pem \
     --private-key /secure/path/companion-key.pem

   axcess-companion run \
     --server https://axcess.example.umich.edu \
     --enrollment-id <claimed-enrollment-id> \
     --certificate /secure/path/companion-cert.pem \
     --private-key /secure/path/companion-key.pem
   ```

   `audit protected-companion pair` and `audit protected-companion run` remain
   compatible aliases for installations that already use the main Axcess CLI.

5. Complete the application sign-in and MFA yourself in the visible browser.
   When the browser has returned to an approved application origin, press
   Enter in the terminal. Do not paste a password, OTP, passkey, or recovery
   code into Axcess.
6. The companion verifies the returned application origin, then tightens its
   route policy and starts the crawl. If it sees an expired session, login
   redirect, 401/403, or required re-verification, it stops with
   `authentication_required`, closes the session, and requires a new manual
   sign-in before any continuation.
7. Review the protected report through the proxy-authorized UI. Public list,
   token-only, normal export, diff, MCP/chat, webhook, and external-model paths
   must not be used for protected evidence. After a report is completed and
   before protected-evidence cleanup, use **Download redacted summary**. It
   issues the explicit same-origin `POST
   /api/protected-scans/{scanId}/exports/redacted`; Axcess checks the proxy
   assertion, report-owner permission, completion/retention state, and records
   the download. It returns a minimal Markdown file directly from memory with
   no server-side export artifact and `no-store` response headers. It omits
   target URLs, page locations, selectors, screenshots, OCR text, attachments,
   and session/browser material. The recipient controls the downloaded copy
   and is responsible for protecting and deleting it.

## Crawl and egress rules

The companion uses a browser context rather than the anonymous public `httpx`
fetcher. The same approved authenticated scope is used for browser checks and
Alfa. Alfa receives a one-use state object over its local inherited stdin
only; it does not receive a state file or a reusable profile.

The companion and the receiving repository both enforce the approved
`max_pages` budget; the persisted index additionally has an absolute cap of
10,000 opaque pages. A replay of an already-indexed opaque page key remains
idempotent, but a new page beyond the budget is refused. This limits a faulty
or compromised companion's ability to exhaust local SQLite storage without
turning a lost response into a false scan failure.

Protected image analysis is deliberately narrow: any raster-image processing
is bounded and in memory only, is not persisted as a blob or screenshot, and
returns only an aggregate image-of-text lead. It is not a general image
downloader or evidence-attachment path. Inline SVG text may also produce an
aggregate lead. Do not treat an absent protected-image lead as proof that all
protected images were evaluated; the report's enabled/skipped-method context
and manual review remain authoritative.

For every seed, navigation, redirect, popup, worker, request, and resource,
the policy validates the exact origin and freshly resolves the hostname. It
rejects non-HTTPS schemes, URL userinfo, sensitive query parameters, wildcard
or cross-origin expansion, IP literals, localhost/private/metadata/reserved
addresses, and DNS-rebinding answers. During the brief human sign-in phase,
only explicitly approved target/IdP origins may use the narrow `POST`/OAuth or
SAML redirect exception. Once the auditor confirms the return to the target,
the crawl permits only `GET`/`HEAD` to the target and explicitly approved CDN
origins.

Downloads, popups, service workers, external form actions, and other mutating
methods are blocked. This is risk reduction, not proof of non-destructive
behavior: owner authorization and a dedicated audit account are still
required. See OWASP's [SSRF Prevention Cheat
Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
for the threat model behind per-request origin and IP validation.

## Evidence, retention, and AI

Protected evidence follows a stricter storage model than a public report:

- Browser session material is ephemeral and local. It is excluded from SQLite,
  config JSON, logs, exports, environment variables, CLI arguments,
  application-managed temporary state files, and the public blob store. The
  dedicated Chromium profile/cache is the documented OS-temporary exception;
  it is `0700`, cleaned immediately and at next companion startup after a
  crash, and must reside on encrypted OS ephemeral storage in production.
- The ordinary SQLite records contain only a non-sensitive issue index, a
  redacted audit history, scope counts, and deployment-HMAC-derived scope
  tags. Exact approved origins live only in the encrypted scan-bound work
  specification. Companion artifact uploads and reviewer attachment uploads
  are disabled in v1.
- Raw HTML, raw protected image blobs, and automatic screenshots are not
  persisted. Any enabled protected-image pass is bounded and in memory only,
  and retains only an aggregate lead.
- At seven days, Axcess first asks the configured KMS to irreversibly destroy
  or revoke the per-scan key/grant, then removes encrypted protected records
  and the wrapped scan data key, retaining only the non-sensitive audit
  metadata. This is crypto-erasure only when the production KMS provides that
  irreversible per-scan operation. `DeterministicLocalKms` is development-only
  and cannot make historical SQLite/WAL/backup snapshots unreadable.
  Operational backups and any recipient-downloaded export must be governed
  separately by the deployment owner.
- Remote model providers, MCP/chat, and webhooks are disabled for protected
  reports. Local Ollama processing is opt-in only after a data-handling
  acknowledgement and verification on both the service and the companion that
  its endpoint uses a **literal loopback IP address** (for example,
  `http://127.0.0.1:11434` or `http://[::1]:11434`; `localhost` is not
  accepted). It may receive only bounded in-memory image bytes, never a page
  dump. Treat an enabled local model as access to protected content, not as a
  conformance verdict.

Redaction is defence in depth, not permission to save a secret. Protected
reports do not accept the legacy free-text manual-check rationale/evidence
paths, and v1 has no in-app attachment or companion-artifact upload flow.
Never place a password, session value, authentication URL/token, personal
identifier, or unreviewed page dump into an approval field or outcome control.

### Required retention maintenance

The web process makes a best-effort cleanup attempt at startup and while it is
running, but that is **not** the production retention control: a local/LAN host
can be off at the seven-day boundary. Every protected deployment must configure
an approved vault factory and schedule the independent command below at least
daily (hourly is recommended), with catch-up and an alert on any non-zero exit:

```bash
# Administrator-owned code only; this is a module reference, not a secret.
AUDIT_PROTECTED_KMS_VAULT_FACTORY=um_axcess_kms:build_protected_vault

# Runs no browser and accepts no scan IDs, URLs, credentials, or key material.
audit protected-maintenance
# equivalent convenience target from the Axcess checkout:
make protected-maintenance
```

`build_protected_vault(settings)` must return an `audit.protected.crypto.ProtectedVault`
backed by the U-M-approved KMS/secret-manager integration. Provider credentials
belong in that integration's approved workload-identity or secret-manager
mechanism; never put them in this module reference, a command argument, or the
Axcess database. The command refuses a missing factory and the local
`DeterministicLocalKms`, and prints only an aggregate completion count—never
scan IDs, target URLs, stored KMS IDs, or provider errors.

The command cryptographically erases a due report only when its configured
vault's `kms_key_id` exactly matches the identifier persisted with that report
and the vault reports irreversible per-scan key/grant destruction. It
validates the entire due batch before it revokes any key, so a single stock
invocation intentionally refuses a mixed old/new-key batch rather than
partially claiming erasure. A KMS rotation therefore needs an explicit
retention plan: keep a **stable logical** `kms_key_id` whose managed adapter
can unwrap and revoke every still-retained provider-key version, or defer the
rotation until the seven-day window is empty. Changing to only a new vault
makes cleanup fail closed; it never deletes old ciphertext or claims erasure
through the wrong KMS. A future per-key vault registry/filter can make
independently keyed mixed-batch cleanup operationally smoother, but it must
preserve this fail-closed guarantee.

For Linux systemd, use a dedicated non-interactive service with an
administrator-controlled environment file and a persistent timer, for example:

```ini
# /etc/systemd/system/axcess-protected-maintenance.service
[Service]
Type=oneshot
User=axcess
WorkingDirectory=/srv/axcess
EnvironmentFile=/etc/axcess/protected-kms.env
ExecStart=/srv/axcess/.venv/bin/audit protected-maintenance
```

```ini
# /etc/systemd/system/axcess-protected-maintenance.timer
[Timer]
OnCalendar=hourly
Persistent=true
Unit=axcess-protected-maintenance.service

[Install]
WantedBy=timers.target
```

Enable it with `systemctl enable --now axcess-protected-maintenance.timer` and
route a failed service/timer to the U-M operations alert path. On macOS, use an
equivalent `launchd` job with `StartInterval` and `RunAtLoad`; do not rely on a
logged-in browser process. A scheduler provides catch-up after downtime, but a
strict wall-clock deletion guarantee while the host is offline requires a
managed-KMS time-bound grant/key-lifecycle policy as an additional deployment
control.

## WCAG manual review: SC 3.3.8

Protected crawling can begin after MFA, but it cannot demonstrate that the
authentication experience is accessible. The report's manual-check matrix
therefore includes **WCAG 2.2 AA SC 3.3.8, Accessible Authentication
(Minimum)** as a manual-only check. For every in-scope login/MFA path, the
auditor should manually determine whether the process requires a cognitive
function test—such as solving a puzzle or memorizing/transcribing
information—without an accessible alternative. Record the outcome through the
protected workflow; mark it `not_tested` or `needs_follow_up` when it was not
evaluated. Do not paste authentication details into a manual-check field. If a
reviewed, redacted attachment is necessary, use the separately approved U-M
evidence process; Axcess v1 does not accept it.

Login and IdP pages are deliberately not collected as protected crawl evidence.
If the authentication journey itself is in the evaluation scope, test it
manually under separate owner authorization and document only redacted,
non-secret evidence. The [W3C Understanding SC
3.3.8](https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html)
guidance is the criterion reference.

## Pilot and incident checklist

Before enabling a production target, conduct a staging pilot with the target
owner and validate all of these:

- proxy identity/group rejection, configured-header stripping, unique nonce/JTI
  signing for every mutation, HMAC method/path/body-digest binding, mTLS
  certificate binding, one-time enrollment, and replay rejection;
- rejection of a mismatched `Origin`, missing `AUDIT_PROTECTED_PUBLIC_ORIGIN`,
  or attacker-supplied `Host`/`Forwarded` headers when a protected browser
  action or companion command is created;
- origin/redirect/DNS-rebinding/private-address refusal and `GET`/`HEAD`-only
  behavior after authentication;
- password-only and MFA handoff, expiry/re-authentication, IdP return, and
  safe interruption;
- no session material in database, logs, process arguments, exports, or
  companion uploads; dedicated `0700` browser profile/cache cleanup on normal
  exit and after a crash; encrypted OS ephemeral storage in production; and
  seven-day protected-evidence cleanup with production KMS per-scan
  revocation/destruction;
- axe/Alfa parity, bounded in-memory protected-image behavior, redacted export
  denial, and the SC 3.3.8 manual-review workflow; and
- keyboard-only/screen-reader operation of the consent, companion, and error
  recovery UI.

If a session, certificate, or protected export may have been exposed, stop the
companion, notify the target owner/security team, revoke or rotate the
companion identity through the approved PKI/proxy process, and follow the
deployment's incident procedure. Axcess cannot invalidate a target-site
session on the organization's behalf.

For background on browser authentication state and session handling, see
[Playwright authentication guidance](https://playwright.dev/docs/auth) and
[NIST SP 800-63B session guidance](https://pages.nist.gov/800-63-4/sp800-63b/session/).
