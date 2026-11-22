# Local JATS preview

Run the installed CLI, without a checkout or any API key:

```sh
researchwitness ui --no-browser --port 8765 --state-dir /path/to/private/jats-preview
```

Open the printed `http://127.0.0.1:8765/` URL. Omit `--no-browser` to open it
automatically, or use `--port 0` for a free port. The default state directory is
`$XDG_DATA_HOME/researchwitness/jats-preview` (normally
`~/.local/share/researchwitness/jats-preview`), or
`%LOCALAPPDATA%/ResearchWitness/jats-preview` on Windows. Use one server per
state directory and keep it private and unchanged while the server runs.
The CLI rejects an adapter package loaded from a different installation root;
this consistency check is not protection against a compromised Python environment.

## Supported journey

1. Select a local `.xml` or `.nxml` JATS article and an ASCII document ID.
   The upload limit is exactly the installed JATS pipeline's `MAX_SOURCE_BYTES`
   (8 MiB). Text, Markdown and PDF uploads are rejected: **JATS XML only on this
   version**. Renaming a non-JATS file does not make it valid JATS.
2. Optionally select main's table structure, unadjusted odds-ratio, prose flow,
   PRISMA flow, count-total, SD/SE/n or denominator-trace slices. These are the
   existing `jats_product.audit_source` options, not new detectors.
3. Jobs move through queued, running, done or failed. Only queued jobs can be
   cancelled; running audits cannot be interrupted. A failed job can be retried
   by uploading again. Shutdown waits for submitted work. On restart any job
   left queued/running is marked failed, not silently resumed.
4. Review the arithmetic-match, mismatch-candidate and abstention summary,
   manifest SHA-256 and sandboxed full HTML report. Read its coverage and
   assumptions. `paper_error_established` remains false.
5. Export a deterministic ZIP containing `bundle/source.xml`, `bundle/report.json`,
   `bundle/report.html`, `bundle/manifest.json` and top-level `REPLAY.txt`.
   Extract into a new directory, open a terminal there and run the exact pinned
   `researchwitness replay-jats bundle --expected-manifest-sha256 HASH` command
   in REPLAY.txt. Keep REPLAY.txt outside `bundle/`: replay rejects extra bundle
   files. Use the same installed implementation for replay.
   There is **no executable replay launcher**.

## Local attack surface and privacy limits

This is a **local preview, not a custody boundary; any local process that can
reach the port with the right Host can obtain the token**. Do not use it for
reserved evaluation or protected custody. It does not authenticate the person
using the browser or isolate malicious local processes/filesystem changes.
It performs no network retrieval, model calls, PDF execution or external actions.
The session token exists only in server memory and is served in the HTML: **any
local OS account able to reach the loopback port can fetch it**. File permissions
do not authenticate HTTP clients or make a shared machine safe for private sources.

The HTTP adapter is outside the deterministic core. It binds only to 127.0.0.1,
checks the exact Host, per-session API token, Origin and Sec-Fetch-Site, bounds
uploads and HTTP workers, uses fixed server-generated storage names, and supplies
a strict CSP. Reports are shown in a sandboxed iframe with no script permission.
Source names and IDs are displayed as text, not injected HTML. Export verifies
the stored payload hashes against the job's manifest pin before returning bytes.
These are defense-in-depth measures, not an independent security certification.

The state directory contains source bytes, reports and job metadata. Keep it
outside Git, shared/synced folders and public document roots. A history entry's
Delete action removes its local files, not downloads, backups or filesystem
remnants. Deletion is **not secure erasure**. Up to 10 jobs and 512 MiB are
retained; new uploads evict oldest finished jobs as needed. Active jobs cannot
be deleted or evicted. Export evidence before reaching retention limits.
New state/job/bundle directories use owner-only 0o700 permissions and new upload,
metadata and bundle files use 0o600 on POSIX, regardless of a permissive umask.
These do not isolate same-user processes, administrators, existing copies or
filesystem races. Windows permission bits are not an ACL qualification: use a
private account/directory and do not assume cross-account confidentiality.
Windows sockets request exclusive address use before binding; POSIX sockets
permit address reuse for restart. Neither provides HTTP account authentication.

Independent adapter security review still gates any RW-09 preview release and
any use with non-public sources. Protected custody remains out of scope.

Human visual and assistive-technology review is pending. No browser-automation
qualification or scientific-performance claim accompanies this preview.
