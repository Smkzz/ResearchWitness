# Deployment boundary

Synthetic engineering use only; not custody-qualified. Protected custody
**NOT RUN**. Production is disabled pending Sami's separate security review.
No production installation, migration, rollback or installed-asset compatibility
is claimed. Do not use private or reserved material.

The CLI refuses commands lacking --dev-root before identity, ACL or store
preflight. Retained read-only Windows policy helpers and direct storage APIs
are not authorization to operate a protected store. Do not invoke them against
production. The synthetic marker is input validation, not OS isolation.

Future enablement requires a separately reviewed change and evidence for
identity/access separation, installed-code integrity, descendant/temp/log/backup
isolation, independent egress enforcement, source rights and output handling.
This port neither configures nor authorizes those controls. No accounts, ACLs,
network rules or privileges are changed.

The synthetic `recover` command has the same mandatory --dev-root boundary.
It never removes referenced objects or records, and never clears stale
.exclusive-lock files. Stale locks remain STORE_LOCK_HELD_MANUAL_REVIEW_REQUIRED;
no automatic account/process probing or real-root repair is authorized.
